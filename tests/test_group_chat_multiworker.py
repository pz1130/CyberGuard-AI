"""Multi-worker safety tests for group chat (Redis lock / cancel flag / dispatch)."""
import pytest

import app.services.group_chat as gc
from app.services.group_chat import GroupChatSession, GroupChatMessage


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    async def exists(self, k):
        return 1 if k in self.store else 0

    async def delete(self, k):
        return 1 if self.store.pop(k, None) is not None else 0

    async def get(self, k):
        return self.store.get(k)


def _make_session(session_id, *, current_round=0, max_rounds=3, status="active"):
    s = GroupChatSession(
        session_id=session_id, user_id=1, agent_ids=[1, 2],
        max_rounds=max_rounds, current_round=current_round, status=status,
    )
    s.messages.append(GroupChatMessage(role="user", content="hi"))
    return s


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()

    async def _getter():
        return r

    monkeypatch.setattr(gc, "get_redis", _getter)
    return r


@pytest.mark.asyncio
async def test_run_lock_is_exclusive(fake_redis):
    svc = gc.GroupChatService()
    assert await svc.acquire_run_lock("s1") is True
    assert await svc.acquire_run_lock("s1") is False
    assert await svc.is_running("s1") is True
    await svc.release_run_lock("s1")
    assert await svc.is_running("s1") is False


@pytest.mark.asyncio
async def test_cancel_flag_round_trips(fake_redis):
    svc = gc.GroupChatService()
    assert await svc._is_cancelled("s1") is False
    await svc._set_cancel_flag("s1")
    assert await svc._is_cancelled("s1") is True
    await svc._clear_cancel_flag("s1")
    assert await svc._is_cancelled("s1") is False


@pytest.mark.asyncio
async def test_is_running_false_when_redis_down(monkeypatch):
    async def _broken():
        raise ConnectionError("down")
    monkeypatch.setattr(gc, "get_redis", _broken)
    svc = gc.GroupChatService()
    assert await svc.is_running("s1") is False


@pytest.mark.asyncio
async def test_load_session_reads_fresh_redis_not_stale_memory(monkeypatch):
    """A poll on any worker must see the latest persisted state, not a stale
    in-memory copy cached by an earlier load."""
    svc = gc.GroupChatService()

    # Seed an old object in the in-memory map (simulating an earlier load).
    stale = _make_session("s9", current_round=0, max_rounds=5)
    svc._active_sessions["s9"] = stale

    # Redis holds newer state (round advanced by the Celery worker).
    fresh_data = {
        "session_id": "s9", "user_id": 1, "agent_ids": [1, 2],
        "messages": [{"role": "user", "content": "hi", "agent_id": None,
                      "agent_name": None, "timestamp": "t"}],
        "max_rounds": 5, "current_round": 3, "status": "active",
        "created_at": "t",
    }
    captured = {}

    async def fake_get_json(key):
        captured["key"] = key
        return fresh_data

    monkeypatch.setattr(gc.cache, "get_json", fake_get_json)

    loaded = await svc.load_session("s9")
    assert loaded is not None
    assert loaded.current_round == 3  # fresh Redis state, not the stale 0
    assert captured["key"] == "groupchat:session:s9"
