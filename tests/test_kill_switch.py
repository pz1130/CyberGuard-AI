"""Tests for the kill switch service."""
import pytest
from app.services import kill_switch as ks


@pytest.fixture(autouse=True)
async def _clean_kill_switch():
    from app.core.database import get_db_context
    from app.models.kill_switch import KillSwitchState
    from sqlalchemy import delete
    async with get_db_context() as s:
        await s.execute(delete(KillSwitchState))
        await s.commit()
    from app.core.redis_client import RedisCache
    cache = RedisCache()
    await cache.set_json("governance:halt", [], expire=60)
    yield


@pytest.mark.asyncio
async def test_global_halt_blocks_all_then_clears():
    await ks.clear("global")
    assert await ks.is_halted() is False
    await ks.engage("global", by="alice", reason="incident")
    assert await ks.is_halted() is True
    assert await ks.is_halted(agent_id=7) is True
    await ks.clear("global")
    assert await ks.is_halted() is False


@pytest.mark.asyncio
async def test_agent_scoped_halt_is_isolated():
    await ks.clear("global")
    await ks.clear("agent:7")
    await ks.engage("agent:7", by="bob", reason="bad agent")
    assert await ks.is_halted(agent_id=7) is True
    assert await ks.is_halted(agent_id=8) is False
    await ks.clear("agent:7")
