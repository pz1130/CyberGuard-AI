"""Sidecar main loop — JSONL over stdin/stdout. Never binds a port."""
from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from typing import Any, Dict, Optional, TextIO

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.mock_agent import MockAgentHost
from apps.desktop.sidecar.rpc import (
    error_msg,
    event_msg,
    read_request,
    result_msg,
    write_message,
)

logger = logging.getLogger("cyberguard.desktop.sidecar")


class SidecarServer:
    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.agent = MockAgentHost()
        self._lock = asyncio.Lock()

    def _write(self, payload: Dict[str, Any]) -> None:
        write_message(self.stdout, payload)

    async def handle(self, req: Dict[str, Any]) -> None:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        try:
            if method == "ping":
                self._write(result_msg(req_id, {"ok": True, "role": "sidecar", "m1": True}))
                return

            if method == "session.capabilities":
                tier = str(params.get("tier") or "readonly")
                caps = capabilities_for_tier(tier)
                self._write(result_msg(req_id, caps.describe()))
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
                async for ev in self.agent.run(
                    task=task,
                    tier=tier,
                    system_prompt=system_prompt,
                ):
                    self._write(event_msg(req_id, ev))
                self._write(result_msg(req_id, {"ok": True, "done": True}))
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
                # EOF
                break
            try:
                req = read_request(line)
            except Exception as exc:  # noqa: BLE001
                self._write(error_msg(None, "parse_error", str(exc)))
                continue
            if req is None:
                continue
            # Sequential handling keeps stdout ordered; parallel runs can be added later
            await self.handle(req)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Banner to stderr only — stdout is reserved for JSONL
    print(
        "cyberguard-desktop-sidecar m1 mock (jsonl; no listen ports)",
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


if __name__ == "__main__":
    main()
