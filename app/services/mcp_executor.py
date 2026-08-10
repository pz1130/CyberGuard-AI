"""MCP tool execution.

STDIO MCP servers are hosted in the isolated `tool-runner` process; this module
is a thin client that decrypts per-server env (the tool-runner has no encryption
key), then proxies STDIO start/stop/status/call/discovery over HTTP. HTTP-transport
MCP runs in-process here (already stateless and multi-worker safe).
"""
import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

from app.core.security import CredentialField, decrypt_data
from app.models.mcp import MCPServer

logger = logging.getLogger(__name__)

TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")


def _decrypt_env(server: MCPServer) -> dict:
    """Decrypt MCP env. Fail loudly if ciphertext present but unreadable (INV-25)."""
    if not server.env_vars_encrypted:
        return {}
    try:
        return json.loads(decrypt_data(server.env_vars_encrypted, CredentialField.MCP_ENV_VARS))
    except Exception as e:
        name = getattr(server, "name", "?")
        logger.error("MCP server %s: env decrypt failed: %s", name, e)
        raise RuntimeError(
            f"MCP server {name!r}: cannot decrypt env_vars_encrypted"
        ) from e


def _spawn_spec(server: MCPServer) -> dict:
    return {
        "name": server.name,
        "command": server.command or "",
        "args": list(server.args or []),
        "env": _decrypt_env(server),
    }


async def _runner_post(path: str, payload: dict, *, timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{TOOL_RUNNER_URL}{path}",
            headers={"X-Runner-Token": RUNNER_TOKEN},
            json=payload,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"tool-runner {path} failed: {resp.status_code} {resp.text}")
        return resp.json()


# ---- STDIO proxies ----

async def _start_stdio_server(server: MCPServer) -> bool:
    """Start an STDIO MCP server in the tool-runner. Returns True if running."""
    if not server.command:
        return False
    try:
        data = await _runner_post("/mcp/start", _spawn_spec(server))
        return bool(data.get("running"))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "MCP start failed for %s: %s", getattr(server, "name", "?"), e
        )
        return False


async def _stop_stdio_server(server_name: str) -> None:
    try:
        await _runner_post("/mcp/stop", {"name": server_name})
    except Exception as e:  # noqa: BLE001
        logger.warning("MCP stop failed for %s: %s", server_name, e)


async def stdio_status(server_name: str) -> bool:
    """Whether an STDIO server is live in the tool-runner."""
    try:
        data = await _runner_post("/mcp/status", {"name": server_name})
        return bool(data.get("running"))
    except Exception as e:  # noqa: BLE001
        logger.debug("MCP status check failed for %s: %s", server_name, e)
        return False


async def execute_stdio_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    timeout = server.timeout_seconds or 30
    payload = _spawn_spec(server)
    payload.update({
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "timeout": timeout,
    })
    data = await _runner_post("/mcp/rpc", payload, timeout=timeout + 10)
    return data.get("result", {})


async def discover_stdio_tools(server: MCPServer) -> list:
    """Discover tools via JSON-RPC tools/list (proxied to the tool-runner)."""
    timeout = server.timeout_seconds or 30
    payload = _spawn_spec(server)
    payload.update({"method": "tools/list", "params": {}, "timeout": timeout})
    data = await _runner_post("/mcp/rpc", payload, timeout=timeout + 10)
    return (data.get("result") or {}).get("tools", [])


# ---- HTTP MCP tool invocation (in-process; stateless, multi-worker safe) ----

async def execute_http_tool(server: MCPServer, tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a tool via HTTP POST to an MCP server endpoint."""
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
        token = decrypt_data(server.auth_token_encrypted, CredentialField.MCP_AUTH_TOKEN)
        headers["Authorization"] = f"Bearer {token}"

    payload = {
        "jsonrpc": "2.0", "id": "1", "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    async with httpx.AsyncClient(timeout=server.timeout_seconds, verify=parsed.scheme == "https") as client:
        response = await client.post(f"{server.url}/tools/call", headers=headers, json=payload)
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
