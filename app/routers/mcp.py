"""MCP (Model Context Protocol) server configuration router."""
import asyncio
import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.security import encrypt_data, decrypt_data
from app.models.mcp import MCPServer, MCPTool
from app.schemas.mcp import (
    MCPServerCreate, MCPServerUpdate, MCPServerRead,
    MCPToolCreate, MCPToolUpdate, MCPToolRead,
    MCPServerListResponse, MCPToolListResponse,
    MCPToolExecuteRequest, MCPToolExecuteResponse,
)

router = APIRouter()

# Live subprocess handles: server_name → asyncio.subprocess.Process
_live_processes: dict[str, asyncio.subprocess.Process] = {}

# Allowed executable extensions (Windows)
_ALLOWED_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".ps1", ".sh", ""})

# Dangerous environment variables that should never be passed to subprocesses
_DANGEROUS_ENV_VARS = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "LD_DEBUG",
    "BASH_ENV", "ENV", "PROMPT_COMMAND", "PS4",
    "GIT_TRACE_PACKET", "GIT_TRACE", "GIT_TRACE_PERFORMANCE",
    "GIT_TRACE_REFS", "GIT_TRACE_REFS", "GIT_TRACE_PACKET",
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS",
    "SVN_SSH", "PERL5LIB", "PERL5OPT", "PERL5DB",
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
    "NODE_PATH", "NODE_OPTIONS",
    "JAVA_HOME", "CLASSPATH",
    "RUBYOPT", "RUBYLIB",
})


def _validate_command(command: str) -> str:
    """
    Validate that command is a safe absolute path to an allowed executable.
    Raises ValueError if unsafe.
    """
    import os
    if not command:
        raise ValueError("command cannot be empty")
    # Must be absolute path
    if not os.path.isabs(command):
        raise ValueError("command must be an absolute path")
    # Check extension blocklist
    base, ext = os.path.splitext(command)
    if ext.lower() in {".js", ".py", ".rb", ".php", ".pl"}:
        raise ValueError(f"unsafe command extension: {ext}")
    # Command must exist and be executable
    if not os.path.isfile(command):
        raise ValueError(f"command not found: {command}")
    if not os.access(command, os.X_OK):
        raise ValueError(f"command not executable: {command}")
    return command


def _validate_args(args: Optional[list]) -> list:
    """
    Validate that args contain no shell metacharacters.
    Raises ValueError if any arg contains dangerous patterns.
    """
    if not args:
        return []
    # Shell metacharacters that enable command injection
    shell_metachar = re.compile(r'[;&|`$<>\\\'"*?#~=[\]{}()!%^|]', re.UNICODE)
    dangerous_keywords = re.compile(
        r'^\s*(curl|wget|nc|netcat|python|perl|ruby|bash|sh|zsh|'
        r'ncat|openssl|socat|chsh|systemctl|service|reboot|shutdown|'
        r'mkfs|mke2fs|dd|rm\s+-rf|mount|umount)\s*$',
        re.IGNORECASE
    )
    validated = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError(f"arg must be string, got {type(arg).__name__}")
        # Block metacharacters that could break out of argument context
        if shell_metachar.search(arg):
            raise ValueError(f"arg contains disallowed shell metachar: {arg!r}")
        stripped = arg.strip()
        if dangerous_keywords.match(stripped):
            raise ValueError(f"arg contains disallowed keyword: {stripped!r}")
        validated.append(arg)
    return validated


def _sanitize_env(env: dict) -> dict:
    """
    Remove dangerous env vars and return a safe environment for subprocess.
    """
    import os
    safe = {k: v for k, v in env.items() if k not in _DANGEROUS_ENV_VARS}
    # Ensure SHELL is not set or points to safe value
    safe.pop("SHELL", None)
    safe.pop("PATHEXT", None)
    return safe


# ---- STDIO subprocess management ----

async def _start_stdio_server(server: MCPServer) -> bool:
    """Launch an STDIO MCP server as an asyncio subprocess."""
    if server.name in _live_processes:
        return True  # already running

    # Validate command and args before executing
    if not server.command:
        return False
    try:
        validated_command = _validate_command(server.command)
    except ValueError:
        return False

    validated_args: list = []
    try:
        validated_args = _validate_args(server.args)
    except ValueError:
        return False

    try:
        decrypted_env: dict[str, str] = {}
        if server.env_vars_encrypted:
            decrypted_env = json.loads(decrypt_data(server.env_vars_encrypted))

        # Merge with base env, prefer PATH from system
        import os
        base_env = dict(os.environ)
        base_env.update(decrypted_env)
        # Sanitize dangerous env vars before passing to subprocess
        base_env = _sanitize_env(base_env)
        base_env["PATH"] = "/usr/bin:/usr/local/bin:/opt/homebrew/bin"

        # Use asyncio.create_subprocess_exec for non-blocking STDIO
        cmd_args = [validated_command] + validated_args
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            env=base_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _live_processes[server.name] = proc
        return True
    except Exception:
        return False


async def _stop_stdio_server(server_name: str):
    """Terminate a running STDIO server subprocess (asyncio.Process)."""
    proc = _live_processes.pop(server_name, None)
    if proc is None:
        return
    if proc.returncode is not None:
        return  # already exited
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass


async def _execute_stdio_tool(server: MCPServer, tool_name: str, arguments: dict) -> dict:
    """Execute a tool via STDIO JSON-RPC to the subprocess using asyncio."""
    proc = _live_processes.get(server.name)
    if not proc or proc.returncode is not None:
        started = await _start_stdio_server(server)
        if not started:
            raise RuntimeError(f"MCP server {server.name} is not running")
        proc = _live_processes[server.name]

    # Serialize JSON-RPC request — asyncio streams require bytes
    import uuid
    request_id = str(uuid.uuid4())
    json_request = json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }) + "\n"

    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("MCP subprocess has no stdio streams")

    try:
        proc.stdin.write(json_request.encode("utf-8"))
        await proc.stdin.drain()
        # Read response lines until we find one matching our request id
        deadline = asyncio.get_event_loop().time() + (server.timeout_seconds or 30)
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError("MCP server stdout closed")
            try:
                response = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue  # skip non-JSON server log lines
            if response.get("id") != request_id:
                continue  # async notification or other request — skip
            if "error" in response:
                raise RuntimeError(response["error"].get("message", str(response["error"])))
            return response.get("result", {})
    except asyncio.TimeoutError:
        await _stop_stdio_server(server.name)
        raise RuntimeError(f"Tool execution timed out after {server.timeout_seconds}s")


# ---- HTTP MCP tool invocation ----

async def _execute_http_tool(server: MCPServer, tool_name: str, arguments: dict) -> dict:
    """Execute a tool via HTTP POST to an MCP server endpoint."""
    import httpx
    from urllib.parse import urlparse

    # SSRF protection
    if not server.url:
        raise RuntimeError("MCP server has no URL configured")
    parsed = urlparse(server.url)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(f"Disallowed URL scheme: {parsed.scheme}")
    hostname = parsed.hostname or ""
    blocked = {"169.254.169.254", "metadata.google.internal", "metadata.internal",
               "localhost", "127.0.0.1", "0.0.0.0"}
    if hostname in blocked or hostname.startswith(("10.", "172.16.", "172.17.", "172.18.",
                                                   "172.19.", "172.20.", "172.21.", "172.22.",
                                                   "172.23.", "172.24.", "172.25.", "172.26.",
                                                   "172.27.", "172.28.", "172.29.", "172.30.",
                                                   "172.31.", "192.168.")):
        raise RuntimeError(f"Disallowed host in URL: {hostname}")

    headers = dict(server.headers_json or {})
    if server.auth_token_encrypted:
        token = decrypt_data(server.auth_token_encrypted)
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    async with httpx.AsyncClient(timeout=server.timeout_seconds, verify=parsed.scheme == "https") as client:
        response = await client.post(
            f"{server.url}/tools/call",
            headers=headers,
            json=payload,
        )
        if response.status_code != 200:
            raise RuntimeError(f"MCP server returned {response.status_code}: {response.text}")
        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data.get("result", {})


# ---- Server CRUD ----

@router.get("/mcp/servers", response_model=MCPServerListResponse)
async def list_mcp_servers(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """List all configured MCP servers."""
    from sqlalchemy import func
    total_result = await db.execute(select(func.count(MCPServer.id)))
    total = total_result.scalar()
    result = await db.execute(select(MCPServer).offset(skip).limit(limit))
    servers = result.scalars().all()
    return MCPServerListResponse(
        total=total,
        servers=[MCPServerRead.model_validate(s) for s in servers],
    )


@router.post("/mcp/servers", response_model=MCPServerRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    body: MCPServerCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a new MCP server."""
    existing = await db.execute(select(MCPServer).where(MCPServer.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="MCP server name already exists")

    # Encrypt sensitive fields
    env_vars_encrypted = None
    if body.env_vars:
        env_vars_encrypted = encrypt_data(json.dumps(body.env_vars))

    auth_token_encrypted = None
    if body.auth_token:
        auth_token_encrypted = encrypt_data(body.auth_token)

    server = MCPServer(
        name=body.name,
        transport_type=body.transport_type,
        command=body.command,
        args=body.args,
        env_vars_encrypted=env_vars_encrypted,
        url=body.url,
        auth_token_encrypted=auth_token_encrypted,
        headers_json=body.headers,
        description=body.description,
        is_active=body.is_active,
        timeout_seconds=body.timeout,
        metadata_json=body.metadata_json,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    # Auto-start STDIO servers
    if body.transport_type == "stdio" and body.is_active and body.command:
        await _start_stdio_server(server)

    return MCPServerRead.model_validate(server)


@router.put("/mcp/servers/{server_id}", response_model=MCPServerRead)
async def update_mcp_server(
    server_id: int,
    body: MCPServerUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update MCP server configuration."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    # If running, stop first
    await _stop_stdio_server(server.name)

    update_data = body.model_dump(exclude_unset=True)

    # Encrypt env_vars if being updated
    if "env_vars" in update_data and update_data["env_vars"]:
        update_data["env_vars_encrypted"] = encrypt_data(json.dumps(update_data.pop("env_vars")))
    elif "env_vars" in update_data:
        update_data["env_vars_encrypted"] = None

    if "auth_token" in update_data:
        if update_data["auth_token"]:
            update_data["auth_token_encrypted"] = encrypt_data(update_data.pop("auth_token"))
        else:
            update_data["auth_token_encrypted"] = None

    # Map standard field names
    if "timeout" in update_data:
        update_data["timeout_seconds"] = update_data.pop("timeout")
    if "headers" in update_data:
        update_data["headers_json"] = update_data.pop("headers")

    for key, value in update_data.items():
        setattr(server, key, value)

    await db.commit()
    await db.refresh(server)

    # Restart if active
    if server.is_active and server.transport_type == "stdio" and server.command:
        await _start_stdio_server(server)

    return MCPServerRead.model_validate(server)


@router.delete("/mcp/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Delete an MCP server."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await _stop_stdio_server(server.name)
    # Use SQL deletes for backward compatibility with older DB schemas
    # where ORM relationship loading may fail due to missing columns.
    await db.execute(text("DELETE FROM mcp_tools WHERE server_id = :server_id"), {"server_id": server_id})
    await db.execute(text("DELETE FROM mcp_servers WHERE id = :server_id"), {"server_id": server_id})
    await db.commit()


@router.post("/mcp/servers/{server_id}/start")
async def start_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Manually start an STDIO MCP server subprocess."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    if server.transport_type != "stdio":
        raise HTTPException(status_code=400, detail="Only STDIO servers can be started manually")

    success = await _start_stdio_server(server)
    if success:
        return {"status": "running", "server": server.name}
    raise HTTPException(status_code=500, detail="Failed to start server")


@router.post("/mcp/servers/{server_id}/stop")
async def stop_mcp_server(
    server_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Manually stop an STDIO MCP server subprocess."""
    result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    await _stop_stdio_server(server.name)
    return {"status": "stopped", "server": server.name}


async def _discover_tools_via_jsonrpc(server: MCPServer) -> list[dict]:
    """Send JSON-RPC tools/list and return discovered tool descriptors."""
    import uuid as _uuid
    request_id = str(_uuid.uuid4())
    payload = {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}

    if server.transport_type == "stdio":
        proc = _live_processes.get(server.name)
        if not proc or proc.returncode is not None:
            await _start_stdio_server(server)
            proc = _live_processes.get(server.name)
        if not proc or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MCP subprocess not running")

        proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await proc.stdin.drain()
        deadline = asyncio.get_event_loop().time() + (server.timeout_seconds or 30)
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError("tools/list timed out")
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError("MCP server stdout closed")
            try:
                resp = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue
            if resp.get("id") != request_id:
                continue
            if "error" in resp:
                raise RuntimeError(resp["error"].get("message", "tools/list error"))
            return resp.get("result", {}).get("tools", [])

    # HTTP transport
    import httpx
    from urllib.parse import urlparse
    if server.url:
        parsed = urlparse(server.url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError(f"Disallowed scheme: {parsed.scheme}")
        hostname = parsed.hostname or ""
        blocked = {"169.254.169.254", "metadata.google.internal", "metadata.internal",
                   "localhost", "127.0.0.1", "0.0.0.0"}
        if hostname in blocked or hostname.startswith(("10.", "172.16.", "172.17.", "172.18.",
                                                       "172.19.", "172.20.", "172.21.", "172.22.",
                                                       "172.23.", "172.24.", "172.25.", "172.26.",
                                                       "172.27.", "172.28.", "172.29.", "172.30.",
                                                       "172.31.", "192.168.")):
            raise RuntimeError(f"Disallowed host: {hostname}")
    headers = dict(server.headers_json or {})
    if server.auth_token_encrypted:
        headers["Authorization"] = f"Bearer {decrypt_data(server.auth_token_encrypted)}"
    async with httpx.AsyncClient(timeout=server.timeout_seconds or 30,
                                 verify=(parsed.scheme == "https") if server.url else True) as client:
        r = await client.post(server.url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "tools/list error"))
        return data.get("result", {}).get("tools", [])


@router.get("/mcp/servers/{server_id}/tools", response_model=MCPToolListResponse)
async def list_server_tools(
    server_id: int,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """
    List tools registered for a server.
    If `refresh=true`, queries the live server via JSON-RPC `tools/list`
    and upserts discovered tools into the DB.
    """
    server_result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = server_result.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    if refresh:
        try:
            discovered = await _discover_tools_via_jsonrpc(server)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Tool discovery failed: {e}")

        for descriptor in discovered:
            name = descriptor.get("name")
            if not name:
                continue
            existing = await db.execute(
                select(MCPTool).where(MCPTool.server_id == server_id, MCPTool.tool_name == name)
            )
            row = existing.scalar_one_or_none()
            schema_json = json.dumps(descriptor["inputSchema"]) if descriptor.get("inputSchema") else None
            if row:
                row.description = descriptor.get("description") or row.description
                if schema_json:
                    row.input_schema_json = schema_json
            else:
                db.add(MCPTool(
                    server_id=server_id,
                    tool_name=name,
                    description=descriptor.get("description"),
                    input_schema_json=schema_json,
                    is_active=True,
                ))
        await db.commit()

    result = await db.execute(
        select(MCPTool).where(MCPTool.server_id == server_id, MCPTool.is_active == True)
    )
    tools = result.scalars().all()
    return MCPToolListResponse(total=len(tools), tools=[MCPToolRead.model_validate(t) for t in tools])


# ---- Tool CRUD ----

@router.post("/mcp/tools", response_model=MCPToolRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_tool(
    body: MCPToolCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Register a tool exposed by an MCP server."""
    server_result = await db.execute(select(MCPServer).where(MCPServer.id == body.server_id))
    if not server_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="MCP server not found")

    tool = MCPTool(**body.model_dump())
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return MCPToolRead.model_validate(tool)


@router.put("/mcp/tools/{tool_id}", response_model=MCPToolRead)
async def update_mcp_tool(
    tool_id: int,
    body: MCPToolUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Update an MCP tool."""
    result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP tool not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(tool, key, value)

    await db.commit()
    await db.refresh(tool)
    return MCPToolRead.model_validate(tool)


@router.delete("/mcp/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_WRITE)),
):
    """Delete an MCP tool."""
    result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP tool not found")
    await db.delete(tool)
    await db.commit()


@router.post("/mcp/tools/execute", response_model=MCPToolExecuteResponse)
async def execute_mcp_tool(
    body: MCPToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(Permission.TASK_EXECUTE)),
):
    """Execute an MCP tool and return results."""
    import time, uuid
    start = time.monotonic()

    tool_result = await db.execute(select(MCPTool).where(MCPTool.id == body.tool_id))
    tool = tool_result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="MCP tool not found")

    server_result = await db.execute(select(MCPServer).where(MCPServer.id == tool.server_id))
    server = server_result.scalar_one_or_none()
    if not server or not server.is_active:
        raise HTTPException(status_code=400, detail="MCP server is not available")

    # P2-2: Per-tool RBAC enforcement
    # A tool can optionally declare a required_permission (e.g. 'knowledge:write').
    # If set, the calling user's role must possess that permission in addition to TASK_EXECUTE.
    if tool.required_permission:
        try:
            required_perm = Permission(tool.required_permission)
        except ValueError:
            raise HTTPException(
                status_code=500,
                detail=f"Tool '{tool.tool_name}' has an invalid required_permission: "
                       f"'{tool.required_permission}'",
            )
        user_role = Role(current_user.role)
        from app.core.rbac import has_permission as _has_permission
        if not _has_permission(user_role, required_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permission denied. Tool '{tool.tool_name}' requires "
                    f"'{tool.required_permission}', but your role '{current_user.role}' "
                    f"does not have it."
                ),
            )

    try:
        if server.transport_type == "stdio":
            result = await _execute_stdio_tool(server, tool.tool_name, body.arguments)
        else:
            result = await _execute_http_tool(server, tool.tool_name, body.arguments)

        # Update usage stats
        tool.use_count += 1
        from datetime import datetime
        tool.last_used_at = datetime.utcnow()
        await db.commit()

        execution_time_ms = (time.monotonic() - start) * 1000
        return MCPToolExecuteResponse(
            tool_id=tool.id,
            tool_name=tool.tool_name,
            status="completed",
            result=result,
            execution_time_ms=round(execution_time_ms, 2),
        )
    except Exception as e:
        execution_time_ms = (time.monotonic() - start) * 1000
        return MCPToolExecuteResponse(
            tool_id=tool.id,
            tool_name=tool.tool_name,
            status="failed",
            error=str(e),
            execution_time_ms=round(execution_time_ms, 2),
        )


@router.get("/mcp/tools/all", response_model=MCPToolListResponse)
async def list_all_mcp_tools(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AGENT_READ)),
):
    """
    List all active MCP tools across all servers.
    Used by the agent config UI to select which tools to expose to a sub-agent.
    """
    result = await db.execute(
        select(MCPTool, MCPServer.name.label("server_name"))
        .join(MCPServer, MCPTool.server_id == MCPServer.id)
        .where(MCPTool.is_active == True, MCPServer.is_active == True)
        .order_by(MCPServer.name, MCPTool.tool_name)
    )
    rows = result.all()
    tools = []
    for row in rows:
        tool = row[0]
        tools.append(MCPToolRead.model_validate(tool))
    return MCPToolListResponse(total=len(tools), tools=tools)
