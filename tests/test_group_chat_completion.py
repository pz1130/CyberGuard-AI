"""Regression tests for the group-chat run_to_completion loop.

Incident: a group-chat `/complete` request pinned the API event loop at 100% CPU
and starved every other request (login included). Root cause: while
`run_to_completion` held a session reference, a concurrent `load_session()` swapped
`_active_sessions[session_id]` for a fresh object. `run_round` then mutated the new
object while the loop condition kept reading the stale one — a non-yielding infinite
busy-loop. These tests pin the loop's termination guarantees.
"""
import asyncio

import pytest

from app.services.group_chat import GroupChatService, GroupChatSession, GroupChatMessage


def _make_session(session_id: str, *, current_round: int, max_rounds: int) -> GroupChatSession:
    s = GroupChatSession(
        session_id=session_id,
        user_id=1,
        agent_ids=[1, 2],
        max_rounds=max_rounds,
        current_round=current_round,
        status="active",
    )
    s.messages.append(GroupChatMessage(role="user", content="hi"))
    return s


@pytest.mark.asyncio
async def test_run_to_completion_terminates_when_session_object_swapped(monkeypatch):
    """The original hang: the in-memory session object is replaced mid-run.

    With the bug, run_to_completion spins forever. The fix re-reads the live
    session each iteration (and honours run_round's max_rounds_reached signal),
    so the call must return well within the timeout.
    """
    service = GroupChatService()
    sid = "swap-test"

    stale = _make_session(sid, current_round=0, max_rounds=3)
    service._active_sessions[sid] = stale

    async def fake_run_round(session_id):
        # Simulate a concurrent load_session() replacing the shared object with a
        # fresh one that is already at the round cap.
        swapped = _make_session(session_id, current_round=3, max_rounds=3)
        service._active_sessions[session_id] = swapped
        return {"status": "max_rounds_reached", "session_id": session_id}

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())

    result = await asyncio.wait_for(service.run_to_completion(sid), timeout=5)
    assert result["session_id"] == sid


@pytest.mark.asyncio
async def test_run_to_completion_stops_at_max_rounds(monkeypatch):
    """Normal path: loop advances current_round and stops at max_rounds."""
    service = GroupChatService()
    sid = "max-rounds-test"
    service._active_sessions[sid] = _make_session(sid, current_round=0, max_rounds=2)

    calls = {"n": 0}

    async def fake_run_round(session_id):
        sess = service._active_sessions[session_id]
        if sess.current_round >= sess.max_rounds:
            return {"status": "max_rounds_reached", "session_id": session_id}
        sess.current_round += 1
        calls["n"] += 1
        return {"session_id": session_id, "round": sess.current_round, "responses": []}

    async def no_consensus(_session):
        return False

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_check_consensus", no_consensus)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())

    result = await asyncio.wait_for(service.run_to_completion(sid), timeout=5)
    assert calls["n"] == 2  # exactly max_rounds productive rounds
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_start_completion_runs_in_background_and_clears_running(monkeypatch):
    """start_completion returns immediately; the run proceeds in the background
    and clears the running flag when done."""
    service = GroupChatService()
    sid = "bg"
    service._active_sessions[sid] = _make_session(sid, current_round=0, max_rounds=1)

    started = asyncio.Event()
    gate = asyncio.Event()

    async def fake_run_round(session_id):
        started.set()
        await gate.wait()
        sess = service._active_sessions[session_id]
        sess.current_round = sess.max_rounds
        return {"session_id": session_id, "round": sess.current_round, "responses": []}

    async def no_consensus(_session):
        return False

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_check_consensus", no_consensus)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())

    await service.start_completion(sid)  # must return without awaiting the run

    await asyncio.wait_for(started.wait(), timeout=2)
    assert service.is_running(sid) is True
    task = service._completion_tasks[sid]

    gate.set()
    await asyncio.wait_for(task, timeout=2)

    assert service.is_running(sid) is False
    assert service._active_sessions[sid].status == "completed"


@pytest.mark.asyncio
async def test_start_completion_is_idempotent_while_running(monkeypatch):
    """A second start_completion while one is in flight must not start a second
    task — this is the structural guard against the original concurrent-run hang."""
    service = GroupChatService()
    sid = "idem"
    service._active_sessions[sid] = _make_session(sid, current_round=0, max_rounds=1)

    started = asyncio.Event()
    gate = asyncio.Event()

    async def fake_run_round(session_id):
        started.set()
        await gate.wait()
        sess = service._active_sessions[session_id]
        sess.current_round = sess.max_rounds
        return {"session_id": session_id, "round": sess.current_round, "responses": []}

    async def no_consensus(_session):
        return False

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_check_consensus", no_consensus)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())

    await service.start_completion(sid)
    await asyncio.wait_for(started.wait(), timeout=2)
    task = service._completion_tasks[sid]

    await service.start_completion(sid)  # second call while running
    assert service._completion_tasks[sid] is task  # same task, not replaced

    gate.set()
    await asyncio.wait_for(task, timeout=2)
    assert service.is_running(sid) is False


@pytest.mark.asyncio
async def test_cancel_session_stops_inflight_run(monkeypatch):
    """Cancelling a session stops the background run and clears running."""
    service = GroupChatService()
    sid = "cancel"
    service._active_sessions[sid] = _make_session(sid, current_round=0, max_rounds=5)

    started = asyncio.Event()
    gate = asyncio.Event()  # never released — simulates a long round

    async def fake_run_round(session_id):
        started.set()
        await gate.wait()
        return {"session_id": session_id, "round": 1, "responses": []}

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())

    await service.start_completion(sid)
    await asyncio.wait_for(started.wait(), timeout=2)
    task = service._completion_tasks[sid]

    ok = await service.cancel_session(sid)
    assert ok is True
    assert service._active_sessions[sid].status == "cancelled"

    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.is_running(sid) is False


async def _noop():
    return None
