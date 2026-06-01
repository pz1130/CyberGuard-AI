"""MCP (Model Context Protocol) server configuration router."""
import asyncio
import json
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
from app.services.mcp_executor import (
    _start_stdio_server,
    _stop_stdio_server,
    stdio_status,
    discover_stdio_tools,
    execute_mcp_tool as _svc_execute_mcp_tool,
)

router = APIRouter()

# Allowed executable extensions (Windows)
_ALLOWED_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".ps1", ".sh", ""})



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
        return await discover_stdio_tools(server)

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
        select(MCPTool).where(MCPTool.server_id == server_id, MCPTool.is_active.is_(True))
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
        result = await _svc_execute_mcp_tool(server, tool.tool_name, body.arguments)

        # Update usage stats
        tool.use_count += 1
        from datetime import datetime, timezone
        # The mcp_tools.last_used_at column is naive DateTime (project
        # convention). Strip tzinfo so the value fits the column.
        tool.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
    tag: Optional[str] = None,
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
        .where(MCPTool.is_active.is_(True), MCPServer.is_active.is_(True))
        .order_by(MCPServer.name, MCPTool.tool_name)
    )
    rows = result.all()
    tools = []
    for row in rows:
        tool = row[0]
        tools.append(MCPToolRead.model_validate(tool))
    if tag:
        tools = [t for t in tools if tag in (t.tags or [])]
    return MCPToolListResponse(total=len(tools), tools=tools)
