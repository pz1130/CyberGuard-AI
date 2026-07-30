"""MCP connector process registry (M1 skeleton — spawn mock children only).

Real MCP protocol client is future work; this module owns lifecycle so
orphan governance can be tested without a live MCP server binary.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.desktop.sidecar.process_group import REGISTRY
from apps.desktop.sidecar.paths import tmp_dir

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
                }
            )
        return out

    def spawn_mock(self, server_id: str, *, hold_seconds: float = 3600) -> dict:
        """Spawn a long-lived mock child (sleep) to exercise orphan cleanup.

        Uses the same process group as the sidecar when possible.
        """
        if server_id in self._children and self._children[server_id].process.poll() is None:
            raise RuntimeError(f"mcp server already running: {server_id}")

        # Marker file under managed tmp (never system /tmp for sensitive work)
        marker = tmp_dir() / f"mcp-{server_id}.marker"
        marker.write_text(f"mock-mcp {server_id}\n", encoding="utf-8")

        # Portable long sleep; Python so we don't depend on /bin/sleep flags
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
        # Start new session member of our group when setsid already done:
        # start_new_session=False keeps child in sidecar's process group on Unix.
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
        if not child:
            return False
        if child.process.poll() is None:
            child.process.terminate()
            try:
                child.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.process.kill()
        REGISTRY.unregister(child.pid)
        del self._children[server_id]
        return True

    def stop_all(self) -> None:
        for sid in list(self._children.keys()):
            self.stop(sid)


MCP = McpManager()
