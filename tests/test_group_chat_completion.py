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
async def test_start_completion_dispatches_under_lock_and_returns(monkeypatch):
    """start_completion acquires the run lock, dispatches the Celery task, and
    returns the session summary. The actual completion now runs in a Celery
    worker, so the in-process task machinery is gone — see
    test_group_chat_multiworker.py for the dispatch-acquire-release contract."""
    service = GroupChatService()
    sid = "bg"
    sess = _make_session(sid, current_round=0, max_rounds=1)
    service._active_sessions[sid] = sess

    async def fake_load(session_id):
        return service._active_sessions[session_id]

    async def no_redis():
        raise ConnectionError("no redis in unit test")

    dispatched = []

    class FakeTask:
        @staticmethod
        def apply_async(args=None, **kwargs):
            dispatched.append(args)

    import app.workers.tasks as tasks_mod
    monkeypatch.setattr(service, "load_session", fake_load)
    monkeypatch.setattr("app.services.group_chat.get_redis", no_redis)
    monkeypatch.setattr(tasks_mod, "run_group_chat_completion_task", FakeTask, raising=False)

    result = await service.start_completion(sid)
    assert result["session_id"] == sid
    # No Redis available → lock not acquired → no Celery dispatch. This
    # confirms the gating: the dispatch only fires when the lock is held.
    assert dispatched == []


@pytest.mark.asyncio
async def test_run_to_completion_is_idempotent_via_status_check(monkeypatch):
    """A second start_completion while one is in flight must not re-run the
    loop. With multi-worker, this is enforced by the Redis lock + Celery
    dispatch-once. Here we verify the loop's own status guard: if the session
    is already 'completed' or 'cancelled' when run_to_completion enters, the
    loop returns without running another round."""
    service = GroupChatService()
    sid = "idem"
    sess = _make_session(sid, current_round=0, max_rounds=1)
    sess.status = "completed"  # already done
    service._active_sessions[sid] = sess

    rounds_run = {"n": 0}

    async def fake_run_round(session_id):
        rounds_run["n"] += 1
        return {"session_id": session_id, "round": 1, "responses": []}

    async def _no_redis():
        raise ConnectionError("no redis in unit test")

    monkeypatch.setattr(service, "run_round", fake_run_round)
    monkeypatch.setattr(service, "_generate_summary", lambda *a, **k: _noop())
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())
    monkeypatch.setattr("app.services.group_chat.get_redis", _no_redis)

    result = await asyncio.wait_for(service.run_to_completion(sid), timeout=5)
    assert rounds_run["n"] == 0
    assert result["session_id"] == sid


@pytest.mark.asyncio
async def test_cancel_session_marks_session_cancelled(monkeypatch):
    """Cancelling a session sets status='cancelled' and persists it.

    Cross-worker cancellation (via the Redis cancel flag) is exercised in
    test_group_chat_multiworker.py. This test pins the local contract: a
    non-existent session returns False, and a known session flips to
    'cancelled'."""
    service = GroupChatService()
    sid = "cancel"
    sess = _make_session(sid, current_round=0, max_rounds=5)
    service._active_sessions[sid] = sess

    async def fake_load(session_id):
        return service._active_sessions.get(session_id)

    async def _no_redis():
        raise ConnectionError("no redis in unit test")

    monkeypatch.setattr(service, "load_session", fake_load)
    monkeypatch.setattr(service, "_persist_session", lambda *a, **k: _noop())
    monkeypatch.setattr("app.services.group_chat.get_redis", _no_redis)

    assert await service.cancel_session("missing") is False
    assert await service.cancel_session(sid) is True
    assert service._active_sessions[sid].status == "cancelled"


async def _noop():
    return None

async def _noop():
    return None
