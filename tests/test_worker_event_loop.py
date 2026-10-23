"""Celery async resources must stay on one process-local event loop."""
import asyncio

from app.core.redis_client import RedisCache
from app.workers import tasks


def test_worker_reuses_event_loop_for_cached_async_clients(monkeypatch):
    clients = []

    class LoopBoundRedis:
        def __init__(self):
            self.loop = asyncio.get_running_loop()
            clients.append(self)

        async def get(self, _key):
            if asyncio.get_running_loop() is not self.loop:
                raise RuntimeError("redis client used from a different event loop")
            return "ok"

    async def make_client():
        return LoopBoundRedis()

    monkeypatch.setattr("app.core.redis_client.get_redis", make_client)
    monkeypatch.setattr(tasks, "_worker_async_loop", None)
    monkeypatch.setattr(tasks, "_worker_async_loop_pid", None)
    cache = RedisCache()

    async def read_cache():
        return await cache.get("health")

    try:
        assert tasks._run_worker_async(read_cache()) == "ok"
        assert tasks._run_worker_async(read_cache()) == "ok"
        assert len(clients) == 1
    finally:
        loop = getattr(tasks, "_worker_async_loop", None)
        if loop is not None and not loop.is_closed():
            loop.close()
