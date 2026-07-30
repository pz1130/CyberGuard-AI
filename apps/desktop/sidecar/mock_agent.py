"""Mock agent host: agent_core.run_loop + mock LLM/tools (M1)."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_core.run_loop import RunLoopConfig, run_loop

from apps.desktop.sidecar.capabilities import SessionCapabilities, capabilities_for_tier


@dataclass
class ActiveRun:
    run_id: str
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    steer_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None


class MockAgentHost:
    def __init__(self) -> None:
        self._runs: Dict[str, ActiveRun] = {}

    def get(self, run_id: str) -> Optional[ActiveRun]:
        return self._runs.get(run_id)

    def abort(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        run.abort_event.set()
        return True

    def steer(self, run_id: str, message: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run.steer_queue.put_nowait(message)
        return True

    async def run(
        self,
        *,
        task: str,
        tier: str = "readonly",
        system_prompt: Optional[str] = None,
        agent_name: str = "desktop-mock",
    ) -> AsyncIterator[Dict[str, Any]]:
        caps = capabilities_for_tier(tier)
        run_id = str(uuid.uuid4())
        active = ActiveRun(run_id=run_id)
        self._runs[run_id] = active

        yield {
            "type": "run_started",
            "run_id": run_id,
            "tier": caps.tier,
            "capabilities": caps.describe(),
        }

        # Mock tool: only available when full tier has exec (still mock)
        tools: Optional[List[Dict[str, Any]]] = None
        if caps.has_local_exec():
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "mock_scan",
                        "description": "Fake scan (M1 mock — no host I/O)",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                        },
                    },
                }
            ]

        step = {"n": 0}

        async def chat(*, messages, tools=None):
            # Simulate latency so abort can interrupt mid-run
            await asyncio.sleep(0.05)
            if active.abort_event.is_set():
                raise RuntimeError("aborted")
            step["n"] += 1
            if tools and step["n"] == 1:
                call = SimpleNamespace(
                    id="mock_call_1",
                    function=SimpleNamespace(
                        name="mock_scan",
                        arguments='{"target":"10.0.0.0/24"}',
                    ),
                )
                return SimpleNamespace(content="", tool_calls=[call])
            # Stream-ish final answer as one chunk (renderer can still show tokens)
            return (
                f"[mock LLM] Task received. Tier={caps.tier}. "
                f"Local exec available={caps.has_local_exec()}. "
                f"Summary: nothing real was scanned (M1 mock)."
            )

        async def dispatch(call):
            await asyncio.sleep(0.05)
            if active.abort_event.is_set():
                return {"status": "error", "error": "aborted", "is_error": True}
            name = call.function.name
            # Even on full tier, this is mock — never touches the host
            return {
                "status": "completed",
                "stdout": f"[mock-tool {name}] args={call.function.arguments}",
                "is_error": False,
            }

        cfg = RunLoopConfig(
            max_steps=6,
            tool_call_budget=10,
            agent_name=agent_name,
            agent_run_id=run_id,
        )
        prompt = system_prompt or (
            "You are CyberGuard desktop mock agent. M1: no real tools or providers."
        )

        try:
            async for ev in run_loop(
                task=task,
                system_prompt=prompt,
                history=[],
                tools=tools,
                config=cfg,
                chat=chat,
                dispatch=dispatch,
                abort_event=active.abort_event,
                steer_queue=active.steer_queue,
            ):
                ev = dict(ev)
                ev.setdefault("run_id", run_id)
                yield ev
        finally:
            self._runs.pop(run_id, None)
