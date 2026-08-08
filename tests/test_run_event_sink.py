"""The audit event stream reaches a durable sink, and a crash leaves a trail.

`AuditBus` emits from the tool pipeline and the run loop, but the
process-default bus ships with zero subscribers — emit was a no-op, so the
evidence trail existed in shape only. A run that dispatched a scan and then
died left nothing to recover from.
"""
import uuid

import pytest
from unittest.mock import AsyncMock

from agent_core.events import AuditBus, AuditEvent, AuditLayer, AuditPhase

from app.services.run_event_log import (
    RunEventSink, find_interrupted_runs, get_run_events, replay_verdict,
    verify_chain,
)


def _event(layer, phase, name, run_id, **kw):
    return AuditEvent(layer=layer, phase=phase, name=name,
                      agent_run_id=run_id, **kw)


# ---- replay classification -------------------------------------------------

@pytest.mark.parametrize("category,expected", [
    ("observe", "safe"),
    ("annotate", "safe"),
    ("remediate", "never"),
    ("contain_hard", "never"),
    ("mutate", "never"),
    ("notify", "never"),          # sending twice is externally visible
    (None, "never"),              # unclassifiable defaults to never
    ("something_new", "never"),
])
def test_replay_verdicts(category, expected):
    assert replay_verdict(category) == expected


# ---- persistence + chain ---------------------------------------------------

@pytest.mark.asyncio
async def test_the_sink_persists_events_in_order_with_an_intact_chain():
    run_id = f"run-{uuid.uuid4()}"
    bus = AuditBus()
    bus.subscribe(RunEventSink(agent_id=9001).handle)

    await bus.emit(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))
    await bus.emit(_event(AuditLayer.TOOL_EXECUTION, AuditPhase.START, "kb_search",
                          run_id, tool_call_id="c1"))
    await bus.emit(_event(AuditLayer.TOOL_EXECUTION, AuditPhase.END, "kb_search",
                          run_id, tool_call_id="c1"))

    rows = await get_run_events(run_id)
    assert [r.seq for r in rows] == [0, 1, 2]
    assert [r.phase for r in rows] == ["start", "start", "end"]
    assert verify_chain(rows) is None


@pytest.mark.asyncio
async def test_a_tampered_payload_breaks_the_chain():
    run_id = f"run-{uuid.uuid4()}"
    sink = RunEventSink(agent_id=9002)
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))
    await sink.handle(_event(AuditLayer.TOOL_EXECUTION, AuditPhase.START, "nmap",
                             run_id, tool_call_id="c1"))

    rows = await get_run_events(run_id)
    assert verify_chain(rows) is None
    rows[1].payload = {"arguments": "something else"}
    assert verify_chain(rows) is not None


@pytest.mark.asyncio
async def test_a_write_failure_propagates_rather_than_disabling_the_sink(monkeypatch):
    """INV-25/29: a failed audit write must abort, not degrade silently."""
    sink = RunEventSink(agent_id=9003)

    async def boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(sink, "_persist", boom)
    with pytest.raises(RuntimeError):
        await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", "run-x"))


# ---- crash recovery --------------------------------------------------------

@pytest.mark.asyncio
async def test_a_dispatched_tool_with_no_result_is_reported_unresolved():
    run_id = f"run-{uuid.uuid4()}"
    sink = RunEventSink(agent_id=9004)
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))
    await sink.handle(_event(
        AuditLayer.TOOL_EXECUTION, AuditPhase.START, "nmap", run_id,
        tool_call_id="c1", payload={"action_category": "remediate"}))
    # ...process dies here: no END event.

    runs = await find_interrupted_runs(agent_id=9004)
    mine = next(r for r in runs if r["run_id"] == run_id)
    assert mine["unresolved_tool_calls"] == [
        {"name": "nmap", "tool_call_id": "c1", "replay": "never"}]
    assert mine["safe_to_replay"] is False
    assert mine["chain_error"] is None


@pytest.mark.asyncio
async def test_a_read_only_interruption_is_marked_safe_to_replay():
    run_id = f"run-{uuid.uuid4()}"
    sink = RunEventSink(agent_id=9005)
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))
    await sink.handle(_event(
        AuditLayer.TOOL_EXECUTION, AuditPhase.START, "kb_search", run_id,
        tool_call_id="c1", payload={"action_category": "observe"}))

    runs = await find_interrupted_runs(agent_id=9005)
    mine = next(r for r in runs if r["run_id"] == run_id)
    assert mine["safe_to_replay"] is True


@pytest.mark.asyncio
async def test_a_finished_run_is_not_reported_as_interrupted():
    run_id = f"run-{uuid.uuid4()}"
    sink = RunEventSink(agent_id=9006)
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.END, "run", run_id))

    runs = await find_interrupted_runs(agent_id=9006)
    assert all(r["run_id"] != run_id for r in runs)


@pytest.mark.asyncio
async def test_the_sweep_ignores_runs_older_than_its_window():
    """The table only grows and every API worker sweeps on boot."""
    from datetime import datetime, timedelta
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.run_event import AgentRunEvent

    run_id = f"run-{uuid.uuid4()}"
    sink = RunEventSink(agent_id=9007)
    await sink.handle(_event(AuditLayer.AGENT, AuditPhase.START, "run", run_id))

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(AgentRunEvent).where(AgentRunEvent.run_id == run_id)
        )).scalars().all()
        for row in rows:
            row.created_at = datetime.utcnow() - timedelta(days=30)
        await s.commit()

    recent = await find_interrupted_runs(agent_id=9007, within_hours=24)
    assert all(r["run_id"] != run_id for r in recent)
    everything = await find_interrupted_runs(agent_id=9007, within_hours=24 * 365)
    assert any(r["run_id"] == run_id for r in everything)


@pytest.mark.asyncio
async def test_events_without_a_run_id_are_dropped_not_crashed():
    """The bus allows a None correlation id; the sink must not blow up on it."""
    sink = RunEventSink(agent_id=9008)
    await sink.handle(AuditEvent(layer=AuditLayer.AGENT, phase=AuditPhase.START,
                                 name="orphan"))
