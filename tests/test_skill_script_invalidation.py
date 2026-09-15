"""A re-import must not launder new code through an old approval."""
from __future__ import annotations

import pytest

from app.models.skill import Tool
from app.routers.skills import invalidate_stale_script_tools


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, tools):
        self.tools = tools

    async def execute(self, _stmt):
        return _Result(self.tools)


def _tool(name, digest, active=True):
    t = Tool(name=name, source_skill_id=1, source_script_path="scripts/x.py",
             source_bundle_digest=digest, script_network="none", is_active=active)
    t.id = abs(hash(name)) % 1000
    return t


@pytest.mark.asyncio
async def test_a_changed_bundle_deactivates_its_tools():
    stale = _tool("stale", "a" * 64)
    db = _DB([stale])
    changed = await invalidate_stale_script_tools(db, 1, "b" * 64)
    assert [t.name for t in changed] == ["stale"]
    assert stale.is_active is False


@pytest.mark.asyncio
async def test_an_unchanged_bundle_leaves_tools_alone():
    same = _tool("same", "c" * 64)
    changed = await invalidate_stale_script_tools(_DB([same]), 1, "c" * 64)
    assert changed == []
    assert same.is_active is True


@pytest.mark.asyncio
async def test_already_inactive_tools_are_not_reported_again():
    off = _tool("off", "a" * 64, active=False)
    assert await invalidate_stale_script_tools(_DB([off]), 1, "b" * 64) == []
