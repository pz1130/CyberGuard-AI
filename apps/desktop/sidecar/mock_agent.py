"""Agent host: agent_core.run_loop + mock or live LLM (M1 / M1.5)."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_core.run_loop import RunLoopConfig, run_loop

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.provider import load_provider_config, live_chat


def _load_builtin_skills() -> str:
    skills_dir = Path(__file__).resolve().parent / "skills"
    if not skills_dir.is_dir():
        return ""
    parts = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            parts.append(path.read_text(encoding="utf-8").strip())
        except OSError:
            continue
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)


@dataclass
class ActiveRun:
    run_id: str
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    steer_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None


class MockAgentHost:
    """Name kept for compatibility; supports mock + live provider modes."""

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
        agent_name: str = "desktop-agent",
    ) -> AsyncIterator[Dict[str, Any]]:
        caps = capabilities_for_tier(tier)
        provider = load_provider_config()
        run_id = str(uuid.uuid4())
        active = ActiveRun(run_id=run_id)
        self._runs[run_id] = active

        yield {
            "type": "run_started",
            "run_id": run_id,
            "tier": caps.tier,
            "capabilities": caps.describe(),
            "provider": provider.public_status(),
        }

        # Tools: still mock until M2 sandbox (safety gate). Live LLM may call them.
        tools: Optional[List[Dict[str, Any]]] = None
        if caps.has_local_exec():
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "mock_scan",
                        "description": "Fake scan (M1 — no host I/O until M2 sandbox)",
                        "parameters": {
                            "type": "object",
                            "properties": {"target": {"type": "string"}},
                            "required": ["target"],
                        },
                    },
                }
            ]

        step = {"n": 0}
        skills = _load_builtin_skills()
        default_prompt = (
            "You are CyberGuard desktop security agent (self-use M1.5).\n"
            "Be precise and actionable. Prefer read-only investigation.\n"
            "Tools named mock_* do not touch the real host.\n"
        )
        if skills:
            default_prompt += "\n## Built-in SOPs\n" + skills
        if not provider.is_live:
            default_prompt += (
                "\n\n(Running in MOCK mode — no real LLM. "
                "Set CYBERGUARD_LLM_MODE=live + API key for real responses.)"
            )
        prompt = system_prompt or default_prompt

        async def chat(*, messages, tools=None):
            if active.abort_event.is_set():
                raise RuntimeError("aborted")
            if provider.is_live:
                return await live_chat(provider, list(messages), tools=tools)

            # ---- mock LLM ----
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
            return (
                f"[mock LLM] Task received. Tier={caps.tier}. "
                f"Local exec available={caps.has_local_exec()}. "
                f"Summary: nothing real was scanned (M1 mock). "
                f"Configure live provider for real analysis."
            )

        async def dispatch(call):
            await asyncio.sleep(0.05)
            if active.abort_event.is_set():
                return {"status": "error", "error": "aborted", "is_error": True}
            name = call.function.name
            # M1/M1.5 safety: tools remain mock until M2 sandbox exit criteria
            return {
                "status": "completed",
                "stdout": f"[mock-tool {name}] args={call.function.arguments}",
                "is_error": False,
            }

        cfg = RunLoopConfig(
            max_steps=8 if provider.is_live else 6,
            tool_call_budget=15 if provider.is_live else 10,
            agent_name=agent_name,
            agent_run_id=run_id,
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
