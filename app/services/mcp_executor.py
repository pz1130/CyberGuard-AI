"""MCP tool execution — reusable across the router and the internal-agent runner."""
import asyncio
import json
import re
from typing import Any, Dict, Optional

from app.core.security import decrypt_data
from app.models.mcp import MCPServer


# Live subprocess handles: server_name → asyncio.subprocess.Process
_live_processes: dict[str, asyncio.subprocess.Process] = {}

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


async def execute_stdio_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
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

async def execute_http_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool via HTTP POST to an MCP server endpoint."""
    import httpx
    from urllib.parse import urlparse
    from app.core.ssrf import validate_outbound_url, SSRFError

    if not server.url:
        raise RuntimeError("MCP server has no URL configured")
    try:
        validate_outbound_url(server.url)
    except SSRFError as e:
        raise RuntimeError(f"SSRF blocked: {e}")
    parsed = urlparse(server.url)

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


async def execute_mcp_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Transport-agnostic entry point. Dispatches by `server.transport_type`."""
    if server.transport_type == "stdio":
        return await execute_stdio_tool(server, tool_name, arguments)
    return await execute_http_tool(server, tool_name, arguments)
