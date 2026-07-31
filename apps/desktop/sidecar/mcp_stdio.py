"""STDIO MCP client for the desktop sidecar (M1.5).

JSON-RPC 2.0 over stdin/stdout, one line per message — same wire shape as
``tool_runner/mcp_host.py``, plus MCP ``initialize`` handshake.

Lazy spawn on first use; processes registered with ProcessRegistry for
orphan governance.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.process_group import REGISTRY

logger = logging.getLogger("cyberguard.desktop.mcp_stdio")


@dataclass
class McpServerConfig:
    """One MCP server entry from mcp_servers.json."""

    id: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    # readonly: exposed on all tiers; if False, only full tier
    readonly: bool = True
    enabled: bool = True
    description: str = ""
    # Env var name that receives this server's Keychain slot secret (M3).
    # Default CYBERGUARD_MCP_SECRET; never log the value.
    secret_env: str = "CYBERGUARD_MCP_SECRET"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "McpServerConfig":
        return cls(
            id=str(data.get("id") or data.get("name") or "mcp"),
            command=str(data.get("command") or ""),
            args=[str(a) for a in (data.get("args") or [])],
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            timeout_seconds=int(data.get("timeout_seconds") or 30),
            readonly=bool(data.get("readonly", True)),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description") or ""),
            secret_env=str(
                data.get("secret_env")
                or data.get("secretEnv")
                or "CYBERGUARD_MCP_SECRET"
            ),
        )


@dataclass
class _LiveServer:
    config: McpServerConfig
    proc: asyncio.subprocess.Process
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initialized: bool = False
    tools_cache: Optional[List[Dict[str, Any]]] = None


class McpStdioClient:
    """Manages multiple STDIO MCP servers and tool discovery/calls."""

    def __init__(self) -> None:
        self._live: Dict[str, _LiveServer] = {}

    def list_running(self) -> List[dict]:
        out = []
        for sid, live in self._live.items():
            alive = live.proc.returncode is None
            out.append(
                {
                    "server_id": sid,
                    "pid": live.proc.pid,
                    "alive": alive,
                    "readonly": live.config.readonly,
                    "command": live.config.command,
                }
            )
        return out

    async def stop(self, server_id: str) -> bool:
        live = self._live.pop(server_id, None)
        if not live:
            return False
        await self._terminate(live)
        return True

    async def stop_all(self) -> None:
        for sid in list(self._live.keys()):
            await self.stop(sid)

    async def _terminate(self, live: _LiveServer) -> None:
        proc = live.proc
        if proc.returncode is not None:
            REGISTRY.unregister(proc.pid)
            return
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        REGISTRY.unregister(proc.pid)
        logger.info("stopped mcp server_id=%s pid=%s", live.config.id, proc.pid)

    async def ensure_started(self, cfg: McpServerConfig) -> _LiveServer:
        live = self._live.get(cfg.id)
        if live and live.proc.returncode is None:
            return live
        if live:
            await self._terminate(live)

        if not cfg.command:
            raise RuntimeError(f"MCP server {cfg.id}: empty command")

        env = dict(os.environ)
        # Static env from config first (must not contain live secrets)
        env.update(cfg.env)
        # M3: inject this server's Keychain/file slot only — never other servers' slots
        secret_injected = False
        try:
            from apps.desktop.sidecar.secrets_store import get_mcp_secret

            secret = get_mcp_secret(cfg.id)
            if secret:
                env_key = (cfg.secret_env or "CYBERGUARD_MCP_SECRET").strip()
                if env_key:
                    env[env_key] = secret
                    secret_injected = True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mcp secret load failed server_id=%s err=%s",
                cfg.id,
                type(exc).__name__,
            )

        proc = await asyncio.create_subprocess_exec(
            cfg.command,
            *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=False,
        )
        REGISTRY.register(proc.pid, f"mcp:{cfg.id}")
        live = _LiveServer(config=cfg, proc=proc)
        self._live[cfg.id] = live
        logger.info(
            "spawned mcp server_id=%s pid=%s cmd=%s secret_injected=%s",
            cfg.id,
            proc.pid,
            cfg.command,
            secret_injected,
        )
        if secret_injected:
            try:
                from apps.desktop.sidecar.audit_chain import append_event

                append_event(
                    "mcp_spawn",
                    {
                        "server_id": cfg.id,
                        "secret_injected": True,
                        "secret_env": cfg.secret_env,
                        # never include secret value
                    },
                    approval_type="self",
                )
            except Exception:  # noqa: BLE001
                pass

        async with live.lock:
            await self._initialize(live)
        return live

    async def _initialize(self, live: _LiveServer) -> None:
        if live.initialized:
            return
        result = await self._rpc(
            live,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cyberguard-desktop", "version": "0.1.5"},
            },
            timeout=live.config.timeout_seconds,
        )
        # notifications/initialized has no id / response
        await self._notify(live, "notifications/initialized", {})
        live.initialized = True
        logger.debug("mcp %s initialized: %s", live.config.id, result)

    async def _notify(
        self, live: _LiveServer, method: str, params: dict
    ) -> None:
        proc = live.proc
        if proc.stdin is None:
            raise RuntimeError("no stdin")
        payload = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params}
        ) + "\n"
        proc.stdin.write(payload.encode("utf-8"))
        await proc.stdin.drain()

    async def _rpc(
        self,
        live: _LiveServer,
        method: str,
        params: Optional[dict],
        *,
        timeout: int,
    ) -> Any:
        proc = live.proc
        if proc.returncode is not None:
            raise RuntimeError(f"MCP server {live.config.id} exited")
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MCP subprocess has no stdio")

        request_id = str(uuid.uuid4())
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        ) + "\n"
        proc.stdin.write(payload.encode("utf-8"))
        await proc.stdin.drain()

        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(1, timeout)
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RuntimeError(
                    f"MCP {live.config.id} RPC {method} timed out after {timeout}s"
                )
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RuntimeError(f"MCP {live.config.id} stdout closed")
            try:
                resp = json.loads(line.decode("utf-8").strip())
            except json.JSONDecodeError:
                continue
            # skip notifications / unrelated
            if resp.get("id") != request_id:
                continue
            if "error" in resp:
                err = resp["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                raise RuntimeError(msg)
            return resp.get("result", {})

    async def list_tools(self, cfg: McpServerConfig, *, force: bool = False) -> List[Dict[str, Any]]:
        live = await self.ensure_started(cfg)
        async with live.lock:
            if live.tools_cache is not None and not force:
                return live.tools_cache
            result = await self._rpc(
                live,
                "tools/list",
                {},
                timeout=cfg.timeout_seconds,
            )
            tools = list((result or {}).get("tools") or [])
            live.tools_cache = tools
            return tools

    async def call_tool(
        self,
        cfg: McpServerConfig,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        live = await self.ensure_started(cfg)
        async with live.lock:
            result = await self._rpc(
                live,
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
                timeout=cfg.timeout_seconds,
            )
            return result


# Process-wide client
STDIO_CLIENT = McpStdioClient()
