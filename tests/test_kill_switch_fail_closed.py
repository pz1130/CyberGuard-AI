"""INV-25: kill switch fails closed on control-plane errors."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_is_halted_fail_closed_on_cache_error(monkeypatch):
    from app.services import kill_switch as ks

    class Boom:
        async def get_json(self, *a, **k):
            raise RuntimeError("redis down")

        async def set_json(self, *a, **k):
            return None

    monkeypatch.setattr(ks, "_cache", Boom())

    async def never_db():
        raise AssertionError("should not reach DB after cache boom without handling")

    # is_halted catches cache error before DB if get_json raises first
    assert await ks.is_halted(agent_id=1) is True


@pytest.mark.asyncio
async def test_is_halted_fail_closed_on_corrupt_scopes(monkeypatch):
    from app.services import kill_switch as ks

    class Bad:
        async def get_json(self, *a, **k):
            return {"not": "a list"}

        async def set_json(self, *a, **k):
            return None

    monkeypatch.setattr(ks, "_cache", Bad())
    assert await ks.is_halted() is True


@pytest.mark.asyncio
async def test_is_halted_global_true(monkeypatch):
    from app.services import kill_switch as ks

    class Ok:
        async def get_json(self, *a, **k):
            return ["global"]

        async def set_json(self, *a, **k):
            return None

    monkeypatch.setattr(ks, "_cache", Ok())
    assert await ks.is_halted(agent_id=99) is True
