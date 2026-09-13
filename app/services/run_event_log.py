"""Durable sink for the agent audit event stream.

``agent_core.events.AuditBus`` emits four layers (agent / turn / message /
tool_execution, each start → update → end) from the tool pipeline and the run
loop — but the process-default bus ships with **zero subscribers**, so emit was
a no-op and the evidence trail existed in shape only.

``RunEventSink`` is that subscriber. Two properties matter:

* **Tool calls are recorded before they execute.** The pipeline emits
  ``tool_execution/start`` ahead of ``before_tool_call``, so a run that
  dispatched a scan and then died leaves a row saying so. A log written after
  the fact is useless for recovery — the interesting case is the process dying
  *during* an action. Each start row carries a ``replay`` verdict so recovery
  can tell a repeatable read from something that must never run twice.
* **Events are hash-chained per run**, like ``audit_logs``, so a missing or
  altered row is detectable.

Writes are **not** best-effort. INV-25 and INV-29 are explicit that a failed
audit write is a security-boundary failure: it must abort, not degrade. A
subscriber that quietly disables itself is the fire-and-forget hole wearing a
different hat.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from agent_core.events import AuditEvent, AuditLayer, AuditPhase

from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.run_event import AgentRunEvent

logger = logging.getLogger(__name__)

_GENESIS = "0" * 64

# How far back the startup recovery sweep looks. Anything older is an audit
# question, not something an operator is still going to act on.
DEFAULT_RECOVERY_WINDOW_HOURS = 48

# Action categories whose effects are externally visible and therefore must not
# be re-executed when recovering a crashed run.
_NEVER_REPLAY = {"contain_soft", "contain_hard", "remediate", "mutate", "notify"}
_SAFE_REPLAY = {"observe", "annotate"}


def replay_verdict(action_category: Optional[str]) -> str:
    """Whether a tool call may be re-executed during recovery.

    Unknown shapes default to "never": re-running something we cannot classify
    is the failure mode with consequences.
    """
    category = (action_category or "").lower()
    if category in _SAFE_REPLAY:
        return "safe"
    if category in _NEVER_REPLAY:
        return "never"
    return "never"


def _canonical(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "[unserializable]"


def _entry_hash(run_id: str, seq: int, layer: str, phase: str, name: str,
                payload: Any, prev_hash: str) -> str:
    return hashlib.sha256(
        f"{run_id}|{seq}|{layer}|{phase}|{name}|{_canonical(payload)}|{prev_hash}".encode()
    ).hexdigest()


class RunEventSink:
    """AuditBus subscriber that persists events, chained per run."""

    def __init__(self, *, agent_id: Optional[int] = None,
                 conversation_id: Optional[int] = None,
                 user_id: Optional[int] = None):
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        # Per-run cursor. Kept in memory for the life of the process; a fresh
        # process re-derives it from the table.
        self._cursor: Dict[str, tuple[int, str]] = {}

    async def handle(self, event: AuditEvent) -> None:
        """Subscriber entry point. Exceptions propagate by design (INV-29)."""
        run_id = event.agent_run_id
        if not run_id:
            # The bus permits a None correlation id; such an event cannot be
            # chained to a run, so there is nothing to persist.
            return
        await self._persist(run_id, event)

    async def _persist(self, run_id: str, event: AuditEvent) -> None:
        seq, prev_hash = await self._cursor_for(run_id)
        layer = event.layer.value if isinstance(event.layer, AuditLayer) else str(event.layer)
        phase = event.phase.value if isinstance(event.phase, AuditPhase) else str(event.phase)
        payload = dict(event.payload or {})
        entry_hash = _entry_hash(run_id, seq, layer, phase, event.name, payload, prev_hash)

        replay = None
        if layer == AuditLayer.TOOL_EXECUTION.value and phase == AuditPhase.START.value:
            replay = replay_verdict(payload.get("action_category"))

        async with AsyncSessionLocal() as session:
            session.add(AgentRunEvent(
                run_id=run_id, seq=seq, agent_id=self.agent_id,
                conversation_id=self.conversation_id, user_id=self.user_id,
                layer=layer, phase=phase, name=event.name,
                turn_id=event.turn_id, tool_call_id=event.tool_call_id,
                payload=payload, replay=replay,
                prev_hash=prev_hash, entry_hash=entry_hash,
            ))
            await session.commit()

        self._cursor[run_id] = (seq + 1, entry_hash)

    async def _cursor_for(self, run_id: str) -> tuple[int, str]:
        cached = self._cursor.get(run_id)
        if cached is not None:
            return cached
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                select(AgentRunEvent)
                .where(AgentRunEvent.run_id == run_id)
                .order_by(AgentRunEvent.seq.desc())
                .limit(1)
            )).scalar_one_or_none()
        if row is None:
            return 0, _GENESIS
        return row.seq + 1, row.entry_hash or _GENESIS


async def get_run_events(run_id: str) -> List[AgentRunEvent]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run_id)
            .order_by(AgentRunEvent.seq)
        )
        return list(result.scalars().all())


def verify_chain(events: List[AgentRunEvent]) -> Optional[str]:
    """Describe the first break in the chain, or None if intact."""
    prev = _GENESIS
    for expected_seq, event in enumerate(events):
        if event.seq != expected_seq:
            return f"seq gap: expected {expected_seq}, found {event.seq}"
        if event.prev_hash != prev:
            return f"broken link at seq {event.seq}"
        recomputed = _entry_hash(event.run_id, event.seq, event.layer, event.phase,
                                 event.name, event.payload, event.prev_hash)
        if recomputed != event.entry_hash:
            return f"payload altered at seq {event.seq}"
        prev = event.entry_hash
    return None


async def find_interrupted_runs(
    agent_id: Optional[int] = None,
    limit: int = 50,
    within_hours: int = DEFAULT_RECOVERY_WINDOW_HOURS,
) -> List[Dict[str, Any]]:
    """Runs that started but never recorded an outcome.

    Each entry reports the tool calls dispatched without a result — the actions
    whose real-world effect is unknown — split by whether they are safe to
    repeat.

    Scoped to ``within_hours`` because this table is append-only and every API
    worker sweeps it on boot: an unbounded scan gets slower for the life of the
    deployment, and a run interrupted last month is archaeology, not recovery.
    """
    cutoff = utc_now() - timedelta(hours=within_hours)
    async with AsyncSessionLocal() as session:
        recent = select(AgentRunEvent.run_id).where(
            AgentRunEvent.layer == AuditLayer.AGENT.value,
            AgentRunEvent.phase == AuditPhase.START.value,
            AgentRunEvent.created_at >= cutoff,
        )
        if agent_id is not None:
            recent = recent.where(AgentRunEvent.agent_id == agent_id)

        rows = list((await session.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id.in_(recent))
            .order_by(AgentRunEvent.run_id, AgentRunEvent.seq)
        )).scalars().all())

    by_run: Dict[str, List[AgentRunEvent]] = {}
    for row in rows:
        by_run.setdefault(row.run_id, []).append(row)

    interrupted: List[Dict[str, Any]] = []
    for run_id, events in by_run.items():
        finished = any(e.layer == AuditLayer.AGENT.value
                       and e.phase == AuditPhase.END.value for e in events)
        if finished:
            continue

        completed = {e.tool_call_id for e in events
                     if e.layer == AuditLayer.TOOL_EXECUTION.value
                     and e.phase == AuditPhase.END.value}
        unresolved = [e for e in events
                      if e.layer == AuditLayer.TOOL_EXECUTION.value
                      and e.phase == AuditPhase.START.value
                      and e.tool_call_id not in completed]

        interrupted.append({
            "run_id": run_id,
            "agent_id": events[0].agent_id,
            "conversation_id": events[0].conversation_id,
            "started_at": events[0].created_at,
            "last_seq": events[-1].seq,
            "unresolved_tool_calls": [
                {"name": e.name, "tool_call_id": e.tool_call_id, "replay": e.replay}
                for e in unresolved
            ],
            "safe_to_replay": all(e.replay == "safe" for e in unresolved),
            "chain_error": verify_chain(events),
        })
        if len(interrupted) >= limit:
            break
    return interrupted
