"""Append-only run log: crash recovery, replay safety, tamper evidence."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner
from app.services.run_event_log import (RunEventLog, find_interrupted_runs,
                                         get_run_events, replay_verdict,
                                         verify_chain)


# ---- replay classification ---------------------------------------------------

@pytest.mark.parametrize("kind,category,expected", [
    ("kb", None, "safe"),
    ("search", None, "safe"),
    ("skill", None, "safe"),
    ("pool", "observe", "safe"),
    ("mcp", "annotate", "safe"),
    ("pool", "remediate", "never"),
    ("pool", "contain_hard", "never"),
    ("mcp", "mutate", "never"),
    ("pool", "notify", "never"),          # sending twice is externally visible
])
def test_replay_verdicts(kind, category, expected):
    assert replay_verdict(kind, category) == expected


@pytest.mark.parametrize("kind,category", [
    ("mcp", None), ("pool", None), ("unknown", "something_new"),
])
def test_unclassifiable_calls_default_to_never_replay(kind, category):
    """Re-running something we cannot classify is the failure with consequences."""
    assert replay_verdict(kind, category) == "never"


# ---- chaining ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_are_chained_and_verify():
    log = RunEventLog(agent_id=1, user_id=None)
    await log.append("run_started", {"task": "scan"})
    await log.append("tool_started", {"tool": "nmap", "call_id": "c1"},
                     replay="never")
    await log.append("tool_result", {"tool": "nmap", "call_id": "c1"})
    await log.append("run_finished", {"outcome": "completed"})

    events = await get_run_events(log.run_id)
    assert [e.event_type for e in events] == [
        "run_started", "tool_started", "tool_result", "run_finished"]
    assert [e.seq for e in events] == [0, 1, 2, 3]
    assert verify_chain(events) is None


@pytest.mark.asyncio
async def test_a_tampered_payload_breaks_the_chain():
    log = RunEventLog(agent_id=1)
    await log.append("run_started", {"task": "scan"})
    await log.append("tool_started", {"tool": "nmap", "call_id": "c1"})

    events = await get_run_events(log.run_id)
    events[0].payload = {"task": "something innocuous"}     # in-memory edit
    assert verify_chain(events) == "payload altered at seq 0"


@pytest.mark.asyncio
async def test_a_missing_event_breaks_the_chain():
    log = RunEventLog(agent_id=1)
    await log.append("run_started", {})
    await log.append("tool_started", {"call_id": "c1"})
    await log.append("tool_result", {"call_id": "c1"})

    events = await get_run_events(log.run_id)
    del events[1]
    assert verify_chain(events) is not None


@pytest.mark.asyncio
async def test_a_failed_write_disables_the_log_without_raising(monkeypatch):
    """Losing the log is bad; taking the agent run down with it is worse."""
    log = RunEventLog(agent_id=1)

    class Boom:
        def __call__(self):
            raise RuntimeError("db gone")
    monkeypatch.setattr("app.services.run_event_log.AsyncSessionLocal", Boom())

    assert await log.append("run_started", {}) is None
    assert log.enabled is False
    assert await log.append("tool_started", {}) is None      # stays quiet


# ---- crash recovery ----------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupted_run_reports_its_unresolved_tool_calls():
    """The case worth recovering from is the process dying mid-scan: the tool
    was dispatched and nothing knows whether it landed."""
    log = RunEventLog(agent_id=4242)
    await log.append("run_started", {"task": "scan the dmz"})
    await log.append("tool_started", {"tool": "nmap", "call_id": "c1"},
                     replay="never")
    # ...crash here: no tool_result, no run_finished.

    # The test database is shared and non-transactional, so match this run
    # rather than assuming it is the only interrupted one on record.
    runs = await find_interrupted_runs(agent_id=4242)
    mine = next(r for r in runs if r["run_id"] == log.run_id)
    assert mine["safe_to_replay"] is False
    assert mine["unresolved_tool_calls"] == [
        {"tool": "nmap", "call_id": "c1", "replay": "never"}]
    assert mine["chain_error"] is None


@pytest.mark.asyncio
async def test_a_read_only_interruption_is_marked_safe_to_replay():
    log = RunEventLog(agent_id=4243)
    await log.append("run_started", {})
    await log.append("tool_started", {"tool": "kb_search", "call_id": "c1"},
                     replay="safe")

    runs = await find_interrupted_runs(agent_id=4243)
    mine = next(r for r in runs if r["run_id"] == log.run_id)
    assert mine["safe_to_replay"] is True


@pytest.mark.asyncio
async def test_completed_runs_are_not_reported_as_interrupted():
    log = RunEventLog(agent_id=4244)
    await log.append("run_started", {})
    await log.append("tool_started", {"tool": "nmap", "call_id": "c1"},
                     replay="never")
    await log.append("tool_result", {"tool": "nmap", "call_id": "c1"})
    await log.append("run_finished", {"outcome": "completed"})

    runs = await find_interrupted_runs(agent_id=4244)
    assert log.run_id not in [r["run_id"] for r in runs]


# ---- wiring into the loop ----------------------------------------------------

def _tool_step(name="grep", call_id="c1"):
    return SimpleNamespace(content="", tool_calls=[SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments='{"q":"x"}'))])


def _runner(monkeypatch, chat_seq, agent_id=9001):
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: SimpleNamespace(
        chat=AsyncMock(side_effect=chat_seq)))
    r = InternalAgentRunner(
        {"id": agent_id, "agent_name": "x", "system_prompt": "sys",
         "llm_provider_id": 1, "llm_model": "m", "tool_loop_max_steps": 6,
         "memory_window": 0, "associated_skills": [],
         "metadata_json": {"mcp_tool_ids": []}, "permission_level": "medium"})
    monkeypatch.setattr(r, "_build_tools", AsyncMock(return_value=[{"type": "function"}]))
    monkeypatch.setattr(r, "_dispatch", AsyncMock(return_value="tool ok"))
    return r


@pytest.mark.asyncio
async def test_a_run_writes_start_tool_and_finish(monkeypatch):
    runner = _runner(monkeypatch, [_tool_step(), "final"])
    await runner.execute(task="go", conversation_id=None, user_id=1)

    events = await get_run_events(runner._run_log.run_id)
    types = [e.event_type for e in events]
    assert types == ["run_started", "tool_started", "tool_result", "run_finished"]
    assert events[-1].payload["outcome"] == "completed"
    assert verify_chain(events) is None


@pytest.mark.asyncio
async def test_tool_started_is_written_before_the_tool_runs(monkeypatch):
    """A row appended after the fact would never exist for the calls that
    matter — the ones interrupted by a crash."""
    runner = _runner(monkeypatch, [_tool_step(), "final"])
    seen = {}

    async def dispatch(call):
        seen["events_at_dispatch"] = [
            e.event_type for e in await get_run_events(runner._run_log.run_id)]
        return "tool ok"
    monkeypatch.setattr(runner, "_dispatch", dispatch)

    await runner.execute(task="go", conversation_id=None, user_id=1)
    assert "tool_started" in seen["events_at_dispatch"]
    assert "tool_result" not in seen["events_at_dispatch"]


@pytest.mark.asyncio
async def test_a_failed_run_still_records_an_outcome(monkeypatch):
    runner = _runner(monkeypatch, RuntimeError("provider down"))
    await runner.execute(task="go", conversation_id=None, user_id=1)

    events = await get_run_events(runner._run_log.run_id)
    assert events[-1].event_type == "run_finished"
    assert events[-1].payload["outcome"] == "failed"


# ---- recovery sweep scope ----------------------------------------------------

@pytest.mark.asyncio
async def test_the_sweep_ignores_runs_older_than_its_window():
    """The startup sweep must not re-read the whole append-only table.

    `agent_run_events` only grows, and every API worker sweeps on boot, so an
    unbounded scan degrades startup for the life of the deployment.
    """
    from datetime import datetime, timedelta

    from app.core.database import AsyncSessionLocal
    from app.models.run_event import AgentRunEvent

    log = RunEventLog(agent_id=4244)
    await log.append("run_started", {})

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(AgentRunEvent).where(AgentRunEvent.run_id == log.run_id)
        )).scalars().all()
        for row in rows:
            row.created_at = datetime.utcnow() - timedelta(days=30)
        await s.commit()

    recent = await find_interrupted_runs(agent_id=4244, within_hours=24)
    assert all(r["run_id"] != log.run_id for r in recent)

    everything = await find_interrupted_runs(agent_id=4244, within_hours=24 * 365)
    assert any(r["run_id"] == log.run_id for r in everything)
