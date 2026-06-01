import unittest
from app.core.versioned_cache import VersionedCache


class FakeRedis:
    """Mimics redis.asyncio with decode_responses=True: get -> str|None, incr -> int."""
    def __init__(self):
        self.store: dict[str, str] = {}
        self.get_calls = 0

    async def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    async def incr(self, key):
        v = int(self.store.get(key, "0")) + 1
        self.store[key] = str(v)
        return v


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("redis down")

    async def incr(self, key):
        raise ConnectionError("redis down")


def _getter(client):
    async def _get():
        return client
    return _get


class TestVersionedCache(unittest.IsolatedAsyncioTestCase):
    async def test_loads_once_then_serves_from_local(self):
        r = FakeRedis()
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return f"value-{calls['n']}"

        c = VersionedCache("master_config", redis_getter=_getter(r))
        self.assertEqual(await c.get(loader), "value-1")
        self.assertEqual(await c.get(loader), "value-1")  # cached, loader not re-called
        self.assertEqual(calls["n"], 1)

    async def test_bump_on_one_instance_invalidates_another(self):
        r = FakeRedis()  # shared "redis" across two cache instances
        a_calls = {"n": 0}
        b_calls = {"n": 0}

        async def a_loader():
            a_calls["n"] += 1
            return f"a-{a_calls['n']}"

        async def b_loader():
            b_calls["n"] += 1
            return f"b-{b_calls['n']}"

        a = VersionedCache("ns", redis_getter=_getter(r))
        b = VersionedCache("ns", redis_getter=_getter(r))
        await a.get(a_loader)            # a caches at version 0
        await b.get(b_loader)            # b caches at version 0
        await a.bump()                   # global version -> 1
        await b.get(b_loader)            # b sees new version -> reloads
        self.assertEqual(b_calls["n"], 2)

    async def test_bump_with_value_adopts_locally_without_reload(self):
        r = FakeRedis()
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return "loaded"

        c = VersionedCache("ns", redis_getter=_getter(r))
        await c.get(loader)              # version 0, 1 load
        await c.bump("written")          # writer adopts new value under new version
        self.assertEqual(await c.get(loader), "written")  # no reload
        self.assertEqual(calls["n"], 1)

    async def test_redis_down_degrades_to_reload_every_read(self):
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return "v"

        c = VersionedCache("ns", redis_getter=_getter(BrokenRedis()))
        await c.get(loader)
        await c.get(loader)
        self.assertEqual(calls["n"], 2)  # never cached because version unknown


if __name__ == "__main__":
    unittest.main()
