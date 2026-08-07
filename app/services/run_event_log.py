"""Append-only run log for internal agents.

Every step of a run is written before or immediately after it happens, so a
crashed run leaves a record of exactly how far it got. Two properties matter:

* **Tool calls are recorded before they execute.** A row written after the fact
  is useless for recovery — the interesting case is the process dying *during*
  a scan. Each `tool_started` row carries a `replay` verdict so recovery can
  tell a repeatable read from an action that must never run twice.
* **Events are hash-chained per run**, like `audit_logs`, so a missing or
  altered row is detectable.

Writes are best-effort: logging must never be the reason an agent run fails.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.run_event import AgentRunEvent

logger = logging.getLogger(__name__)

_GENESIS = "0" * 64

# How far back the startup recovery sweep looks. Anything older is an audit
# question, not something an operator is still going to act on.
DEFAULT_RECOVERY_WINDOW_HOURS = 48

# Action categories whose effects are externally visible and therefore must not
# be re-executed when recovering a crashed run.
_NEVER_REPLAY_CATEGORIES = {"contain_soft", "contain_hard", "remediate", "mutate",
                            "notify"}
# Tool kinds that only read. Repeating them after a crash is free.
_SAFE_REPLAY_KINDS = {"kb", "search", "skill"}


def replay_verdict(kind: str, action_category: Optional[str]) -> str:
    """Decide whether a tool call may be re-executed during recovery.

    Unknown shapes default to "never": re-running something we cannot classify
    is the failure mode with consequences.
    """
    if kind in _SAFE_REPLAY_KINDS:
        return "safe"
    category = (action_category or "").lower()
    if category in _NEVER_REPLAY_CATEGORIES:
        return "never"
    if category in ("observe", "annotate"):
        return "safe"
    return "never"


def _canonical(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "[unserializable]"


class RunEventLog:
    """Writer for one agent run."""

    def __init__(self, *, agent_id: Optional[int] = None,
                 conversation_id: Optional[int] = None,
                 user_id: Optional[int] = None, run_id: Optional[str] = None):
        self.run_id = run_id or str(uuid.uuid4())
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self._seq = 0
        self._prev_hash = _GENESIS
        self.enabled = True

    async def append(self, event_type: str, payload: Optional[Dict[str, Any]] = None,
                     *, replay: Optional[str] = None) -> Optional[int]:
        """Append one event. Returns its seq, or None when the write failed."""
        if not self.enabled:
            return None
        seq = self._seq
        entry_hash = hashlib.sha256(
            (f"{self.run_id}|{seq}|{event_type}|{_canonical(payload)}|"
             f"{self._prev_hash}").encode()
        ).hexdigest()
        try:
            async with AsyncSessionLocal() as session:
                session.add(AgentRunEvent(
                    run_id=self.run_id, seq=seq, agent_id=self.agent_id,
                    conversation_id=self.conversation_id, user_id=self.user_id,
                    event_type=event_type, payload=payload, replay=replay,
                    prev_hash=self._prev_hash, entry_hash=entry_hash,
                ))
                await session.commit()
        except Exception as e:                    # noqa: BLE001
            # Losing the log is bad; taking the agent down with it is worse.
            # Disable further writes so one broken run doesn't spam the logs.
            logger.error("run event log: append %r failed for run %s: %s",
                         event_type, self.run_id, e)
            self.enabled = False
            return None
        self._seq = seq + 1
        self._prev_hash = entry_hash
        return seq


async def get_run_events(run_id: str) -> List[AgentRunEvent]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run_id)
            .order_by(AgentRunEvent.seq)
        )
        return list(result.scalars().all())


def verify_chain(events: List[AgentRunEvent]) -> Optional[str]:
    """Return a description of the first break in the chain, or None if intact."""
    prev = _GENESIS
    for expected_seq, event in enumerate(events):
        if event.seq != expected_seq:
            return f"seq gap: expected {expected_seq}, found {event.seq}"
        if event.prev_hash != prev:
            return f"broken link at seq {event.seq}"
        recomputed = hashlib.sha256(
            (f"{event.run_id}|{event.seq}|{event.event_type}|"
             f"{_canonical(event.payload)}|{event.prev_hash}").encode()
        ).hexdigest()
        if recomputed != event.entry_hash:
            return f"payload altered at seq {event.seq}"
        prev = event.entry_hash
    return None


async def find_interrupted_runs(agent_id: Optional[int] = None,
                                limit: int = 50,
                                within_hours: int = DEFAULT_RECOVERY_WINDOW_HOURS,
                                ) -> List[Dict[str, Any]]:
    """Runs that started but never recorded an outcome.

    Each entry reports the tool calls that were dispatched without a result —
    the actions whose real-world effect is unknown — split by whether they are
    safe to repeat.

    Scoped to ``within_hours`` because this table is append-only and every API
    worker sweeps it on boot: an unbounded scan gets slower for the life of the
    deployment, and a run interrupted last month is an archaeology question, not
    a recovery one.
    """
    cutoff = datetime.utcnow() - timedelta(hours=within_hours)
    async with AsyncSessionLocal() as session:
        recent_runs = select(AgentRunEvent.run_id).where(
            AgentRunEvent.event_type == "run_started",
            AgentRunEvent.created_at >= cutoff,
        )
        if agent_id is not None:
            recent_runs = recent_runs.where(AgentRunEvent.agent_id == agent_id)

        query = (select(AgentRunEvent)
                 .where(AgentRunEvent.run_id.in_(recent_runs))
                 .order_by(AgentRunEvent.run_id, AgentRunEvent.seq))
        rows = list((await session.execute(query)).scalars().all())

    by_run: Dict[str, List[AgentRunEvent]] = {}
    for row in rows:
        by_run.setdefault(row.run_id, []).append(row)

    interrupted: List[Dict[str, Any]] = []
    for run_id, events in by_run.items():
        types = {e.event_type for e in events}
        if "run_started" not in types or "run_finished" in types:
            continue
        completed = {e.payload.get("call_id") for e in events
                     if e.event_type == "tool_result" and e.payload}
        unresolved = [e for e in events
                      if e.event_type == "tool_started"
                      and (e.payload or {}).get("call_id") not in completed]
        interrupted.append({
            "run_id": run_id,
            "agent_id": events[0].agent_id,
            "conversation_id": events[0].conversation_id,
            "started_at": events[0].created_at,
            "last_seq": events[-1].seq,
            "unresolved_tool_calls": [
                {"tool": (e.payload or {}).get("tool"),
                 "call_id": (e.payload or {}).get("call_id"),
                 "replay": e.replay}
                for e in unresolved
            ],
            "safe_to_replay": all(e.replay == "safe" for e in unresolved),
            "chain_error": verify_chain(events),
        })
        if len(interrupted) >= limit:
            break
    return interrupted
