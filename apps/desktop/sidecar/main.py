"""Sidecar main loop — JSONL over stdin/stdout. Never binds a port."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
import traceback
from typing import Any, Dict, Optional, TextIO

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.mcp_manager import MCP
from apps.desktop.sidecar.mock_agent import MockAgentHost
from apps.desktop.sidecar.paths import data_root, logs_dir
from apps.desktop.sidecar.process_group import REGISTRY
from apps.desktop.sidecar.rpc import (
    error_msg,
    event_msg,
    read_request,
    result_msg,
    write_message,
)
from apps.desktop.sidecar.sessions import SessionStore

logger = logging.getLogger("cyberguard.desktop.sidecar")


class SidecarServer:
    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.agent = MockAgentHost()
        self.sessions = SessionStore()
        self._lock = asyncio.Lock()

    def _write(self, payload: Dict[str, Any]) -> None:
        write_message(self.stdout, payload)

    async def handle(self, req: Dict[str, Any]) -> None:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        try:
            if method == "ping":
                from apps.desktop.sidecar.filevault import filevault_status
                from apps.desktop.sidecar.provider import load_provider_config

                self._write(
                    result_msg(
                        req_id,
                        {
                            "ok": True,
                            "role": "sidecar",
                            "m1": True,
                            "data_root": str(data_root()),
                            "provider": load_provider_config().public_status(),
                            "filevault": filevault_status(),
                        },
                    )
                )
                return

            if method == "session.capabilities":
                tier = str(params.get("tier") or "readonly")
                caps = capabilities_for_tier(tier)
                self._write(result_msg(req_id, caps.describe()))
                return

            if method == "sessions.create":
                title = str(params.get("title") or "Untitled")
                tier = str(params.get("tier") or "readonly")
                meta = self.sessions.create(title=title, tier=tier)
                self._write(
                    result_msg(
                        req_id,
                        {
                            "session_id": meta.session_id,
                            "title": meta.title,
                            "tier": meta.tier,
                            "created_at": meta.created_at,
                        },
                    )
                )
                return

            if method == "sessions.list":
                rows = [
                    {
                        "session_id": m.session_id,
                        "title": m.title,
                        "tier": m.tier,
                        "updated_at": m.updated_at,
                        "event_count": m.event_count,
                    }
                    for m in self.sessions.list()
                ]
                self._write(result_msg(req_id, {"sessions": rows}))
                return

            if method == "sessions.events":
                sid = str(params.get("session_id") or "")
                events = list(self.sessions.iter_events(sid))
                self._write(result_msg(req_id, {"session_id": sid, "events": events}))
                return

            if method == "mcp.list":
                self._write(result_msg(req_id, {"servers": MCP.list()}))
                return

            if method == "mcp.spawn_mock":
                server_id = str(params.get("server_id") or "mock-1")
                hold = float(params.get("hold_seconds") or 3600)
                info = MCP.spawn_mock(server_id, hold_seconds=hold)
                self._write(result_msg(req_id, info))
                return

            if method == "mcp.stop":
                server_id = str(params.get("server_id") or "")
                ok = MCP.stop(server_id)
                self._write(result_msg(req_id, {"ok": ok, "server_id": server_id}))
                return

            if method == "agent.abort":
                run_id = str(params.get("run_id") or "")
                ok = self.agent.abort(run_id)
                self._write(result_msg(req_id, {"ok": ok, "run_id": run_id}))
                return

            if method == "agent.steer":
                run_id = str(params.get("run_id") or "")
                message = str(params.get("message") or "")
                ok = self.agent.steer(run_id, message)
                self._write(result_msg(req_id, {"ok": ok, "run_id": run_id}))
                return

            if method == "agent.run":
                task = str(params.get("task") or "")
                if not task:
                    self._write(error_msg(req_id, "bad_params", "task required"))
                    return
                tier = str(params.get("tier") or "readonly")
                system_prompt = params.get("system_prompt")
                session_id = params.get("session_id")
                if not session_id:
                    meta = self.sessions.create(
                        title=(task[:48] + "…") if len(task) > 48 else task,
                        tier=tier,
                    )
                    session_id = meta.session_id
                else:
                    session_id = str(session_id)

                self.sessions.append_event(
                    session_id,
                    {"type": "user_task", "task": task, "tier": tier},
                )

                async for ev in self.agent.run(
                    task=task,
                    tier=tier,
                    system_prompt=system_prompt,
                ):
                    ev = dict(ev)
                    ev["session_id"] = session_id
                    self.sessions.append_event(session_id, ev)
                    self._write(event_msg(req_id, ev))
                self._write(
                    result_msg(
                        req_id,
                        {"ok": True, "done": True, "session_id": session_id},
                    )
                )
                return

            self._write(error_msg(req_id, "unknown_method", f"unknown method: {method}"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("request failed")
            self._write(
                error_msg(req_id, "internal", f"{type(exc).__name__}: {exc}")
            )

    async def run_forever(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, self.stdin.readline)
            if line == "":
                break
            try:
                req = read_request(line)
            except Exception as exc:  # noqa: BLE001
                self._write(error_msg(None, "parse_error", str(exc)))
                continue
            if req is None:
                continue
            await self.handle(req)


def _install_signals() -> None:
    def _shutdown(signum, _frame) -> None:
        logger.info("signal %s — cleanup children", signum)
        MCP.stop_all()
        REGISTRY.kill_all(sig=signal.SIGTERM)
        sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except Exception:
            pass


def main() -> None:
    logs_dir()
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Orphan governance layers ① + ②
    REGISTRY.become_session_leader()
    REGISTRY.install_atexit()
    REGISTRY.start_watchdog(interval_sec=2.0)
    _install_signals()

    print(
        f"cyberguard-desktop-sidecar m1 mock (jsonl; no ports; data={data_root()})",
        file=sys.stderr,
        flush=True,
    )
    server = SidecarServer(sys.stdin, sys.stdout)
    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        MCP.stop_all()
        REGISTRY.kill_all()
        REGISTRY.stop_watchdog()


if __name__ == "__main__":
    main()
