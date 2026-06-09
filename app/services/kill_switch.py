"""Platform-level kill switch (NDB Std §Kill Switch).

Redis is the fast read path; the DB table is the durable source of truth and
is reloaded into Redis on cold start. Checked at the execute_tool chokepoint.
"""
from datetime import datetime
from app.core.redis_client import RedisCache
from app.core.database import get_db_context
from app.models.kill_switch import KillSwitchState
from sqlalchemy import select, delete

_KEY = "governance:halt"
_cache = RedisCache()


async def engage(scope: str, by: str | None, reason: str | None) -> None:
    async with get_db_context() as s:
        existing = (await s.execute(select(KillSwitchState).where(
            KillSwitchState.scope == scope))).scalar_one_or_none()
        if existing is None:
            s.add(KillSwitchState(scope=scope, engaged_by=by, reason=reason,
                                  engaged_at=datetime.utcnow()))
            await s.commit()
    await _refresh_redis()


async def clear(scope: str) -> None:
    async with get_db_context() as s:
        await s.execute(delete(KillSwitchState).where(KillSwitchState.scope == scope))
        await s.commit()
    await _refresh_redis()


async def _engaged_scopes_from_db() -> list[str]:
    async with get_db_context() as s:
        return list((await s.execute(select(KillSwitchState.scope))).scalars().all())


async def _refresh_redis() -> None:
    scopes = await _engaged_scopes_from_db()
    await _cache.set_json(_KEY, scopes, expire=86400)


async def is_halted(agent_id: int | None = None) -> bool:
    scopes = await _cache.get_json(_KEY)
    if scopes is None:
        scopes = await _engaged_scopes_from_db()
        await _cache.set_json(_KEY, scopes, expire=86400)
    if "global" in scopes:
        return True
    return agent_id is not None and f"agent:{agent_id}" in scopes
