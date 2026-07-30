"""MCP connector manager: mock children + real STDIO servers.

- ``spawn_mock`` / ``stop`` — orphan-governance drills (no protocol)
- ``STDIO_CLIENT`` — real MCP JSON-RPC (list/call)
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.mcp_config import load_mcp_servers
from apps.desktop.sidecar.mcp_stdio import STDIO_CLIENT, McpServerConfig
from apps.desktop.sidecar.paths import tmp_dir
from apps.desktop.sidecar.process_group import REGISTRY

logger = logging.getLogger("cyberguard.desktop.mcp_manager")


@dataclass
class McpChild:
    server_id: str
    pid: int
    label: str
    process: subprocess.Popen
    started_at: float = field(default_factory=time.time)


class McpManager:
    def __init__(self) -> None:
        self._children: Dict[str, McpChild] = {}

    def list(self) -> List[dict]:
        out = []
        for c in self._children.values():
            alive = c.process.poll() is None
            out.append(
                {
                    "server_id": c.server_id,
                    "pid": c.pid,
                    "label": c.label,
                    "alive": alive,
                    "started_at": c.started_at,
                    "kind": "mock",
                }
            )
        for row in STDIO_CLIENT.list_running():
            row = dict(row)
            row["kind"] = "stdio"
            out.append(row)
        return out

    def configured_servers(self) -> List[dict]:
        return [
            {
                "id": s.id,
                "command": s.command,
                "args": s.args,
                "readonly": s.readonly,
                "enabled": s.enabled,
                "description": s.description,
            }
            for s in load_mcp_servers()
        ]

    def spawn_mock(self, server_id: str, *, hold_seconds: float = 3600) -> dict:
        if server_id in self._children and self._children[server_id].process.poll() is None:
            raise RuntimeError(f"mcp server already running: {server_id}")

        marker = tmp_dir() / f"mcp-{server_id}.marker"
        marker.write_text(f"mock-mcp {server_id}\n", encoding="utf-8")

        code = (
            "import time,sys;"
            f"open({str(marker)!r},'a').write('running\\n');"
            f"time.sleep({float(hold_seconds)})"
        )
        popen_kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = False

        proc = subprocess.Popen([sys.executable, "-c", code], **popen_kwargs)
        child = McpChild(
            server_id=server_id,
            pid=proc.pid,
            label=f"mcp-mock:{server_id}",
            process=proc,
        )
        self._children[server_id] = child
        REGISTRY.register(proc.pid, child.label)
        logger.info("spawned mock mcp server_id=%s pid=%s", server_id, proc.pid)
        return {"server_id": server_id, "pid": proc.pid, "mock": True}

    def stop(self, server_id: str) -> bool:
        child = self._children.get(server_id)
        if child:
            if child.process.poll() is None:
                child.process.terminate()
                try:
                    child.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.process.kill()
            REGISTRY.unregister(child.pid)
            del self._children[server_id]
            return True
        # try real stdio client (sync wrapper)
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # schedule and hope — prefer await from async callers
                fut = asyncio.ensure_future(STDIO_CLIENT.stop(server_id))
                return True
            return bool(loop.run_until_complete(STDIO_CLIENT.stop(server_id)))
        except Exception:
            return False

    def stop_all(self) -> None:
        for sid in list(self._children.keys()):
            self.stop(sid)
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(STDIO_CLIENT.stop_all())
            else:
                loop.run_until_complete(STDIO_CLIENT.stop_all())
        except Exception:
            pass

    async def stop_all_async(self) -> None:
        for sid in list(self._children.keys()):
            self.stop(sid)
        await STDIO_CLIENT.stop_all()

    async def discover_tools_for_agent(
        self, *, tier: str
    ) -> tuple[List[Dict[str, Any]], Dict[str, tuple[McpServerConfig, str]]]:
        """Return OpenAI-style tool defs + map tool_name -> (server_cfg, mcp_tool_name).

        Tool names are prefixed: ``mcp__{server_id}__{tool_name}`` to avoid clashes.
        readonly servers available on all tiers; non-readonly only on full.
        """
        openai_tools: List[Dict[str, Any]] = []
        routing: Dict[str, tuple[McpServerConfig, str]] = {}

        for cfg in load_mcp_servers():
            if not cfg.enabled:
                continue
            if not cfg.readonly and tier == "readonly":
                continue
            try:
                tools = await STDIO_CLIENT.list_tools(cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP %s list_tools failed: %s", cfg.id, exc)
                continue
            for t in tools:
                raw_name = t.get("name") or "tool"
                exposed = f"mcp__{cfg.id}__{raw_name}"
                desc = t.get("description") or f"MCP tool {raw_name} on {cfg.id}"
                if cfg.readonly:
                    desc = f"[readonly] {desc}"
                schema = t.get("inputSchema") or t.get("input_schema") or {
                    "type": "object",
                    "properties": {},
                }
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": exposed,
                            "description": desc[:500],
                            "parameters": schema,
                        },
                    }
                )
                routing[exposed] = (cfg, raw_name)
        return openai_tools, routing

    async def call_routed(
        self,
        routing: Dict[str, tuple[McpServerConfig, str]],
        exposed_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        if exposed_name not in routing:
            raise RuntimeError(f"unknown MCP tool: {exposed_name}")
        cfg, raw_name = routing[exposed_name]
        return await STDIO_CLIENT.call_tool(cfg, raw_name, arguments or {})


MCP = McpManager()
