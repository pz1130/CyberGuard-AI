"""Skill bodies are disclosed progressively once they get expensive.

Inlining every bound skill's full markdown into the system prompt made every
turn pay for every skill whether or not the task was related — ten 3k-character
skills is ~30k characters resident in context, per turn, forever.
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.internal_agent import InternalAgentRunner, SKILL_INLINE_MAX_TOKENS


def _runner(monkeypatch, bodies, meta=None, **overrides):
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "BASE",
           "associated_skills": sorted(bodies), "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    cfg.update(overrides)
    r = InternalAgentRunner(cfg)
    monkeypatch.setattr(r, "_load_skill_bodies", AsyncMock(return_value=bodies))
    monkeypatch.setattr(r, "_load_skill_meta", AsyncMock(return_value=meta or {
        sid: {"name": f"skill-{sid}", "description": f"does thing {sid}"}
        for sid in bodies}))
    monkeypatch.setattr(r, "_load_mcp_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(r, "_load_pool_tools", AsyncMock(return_value=[]))
    return r


def _big(n_tokens):
    """A body comfortably over the inline budget (4 latin chars ~ 1 token)."""
    return "y" * (n_tokens * 4)


# ---- small skill sets stay inline -------------------------------------------

@pytest.mark.asyncio
async def test_small_skill_set_is_inlined(monkeypatch):
    """Deferring a couple of short skills would waste a whole round-trip."""
    runner = _runner(monkeypatch, {101: "skill A body", 102: "skill B body"})

    prompt = await runner._build_system_prompt()

    assert "skill A body" in prompt and "skill B body" in prompt
    assert runner._skills_deferred is False
    tools = await runner._build_tools()
    assert "load_skill" not in [t["function"]["name"] for t in tools]


# ---- large skill sets switch to a manifest ----------------------------------

@pytest.mark.asyncio
async def test_large_skill_set_becomes_a_manifest(monkeypatch):
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS),
                                    102: _big(100)})

    prompt = await runner._build_system_prompt()

    assert runner._skills_deferred is True
    assert _big(100) not in prompt                 # bodies withheld
    assert "skill_id=101" in prompt and "skill_id=102" in prompt
    assert "does thing 101" in prompt              # description carries selection
    assert "load_skill" in prompt


@pytest.mark.asyncio
async def test_load_skill_tool_is_offered_only_when_deferred(monkeypatch):
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS + 1)})
    tools = await runner._build_tools()
    assert "load_skill" in [t["function"]["name"] for t in tools]


@pytest.mark.asyncio
async def test_manifest_prompt_is_far_smaller_than_the_inlined_one(monkeypatch):
    bodies = {i: _big(400) for i in range(101, 111)}      # 10 skills, ~4k tokens
    runner = _runner(monkeypatch, bodies)

    prompt = await runner._build_system_prompt()

    assert len(prompt) < sum(len(b) for b in bodies.values()) / 10


# ---- fetching a body on demand ----------------------------------------------

def _call(name, **args):
    return SimpleNamespace(id="c1", function=SimpleNamespace(
        name=name, arguments=json.dumps(args)))


@pytest.mark.asyncio
async def test_load_skill_returns_the_body_unfenced(monkeypatch):
    """Skills are operator-authored configuration, not fetched data — fencing
    them as untrusted would tell the model to ignore its own instructions."""
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS + 1)})
    await runner._build_system_prompt()

    out = await runner._dispatch(_call("load_skill", skill_id=101))

    assert out.trusted is True
    assert out.terminate is False
    assert _big(SKILL_INLINE_MAX_TOKENS + 1) in out.text


@pytest.mark.asyncio
async def test_load_skill_rejects_a_skill_not_bound_to_this_agent(monkeypatch):
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS + 1)})
    await runner._build_system_prompt()

    out = await runner._dispatch(_call("load_skill", skill_id=999))

    assert out.status == "error"
    assert "not bound" in out.text


@pytest.mark.asyncio
async def test_load_skill_rejects_a_non_integer_id(monkeypatch):
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS + 1)})
    await runner._build_system_prompt()

    out = await runner._dispatch(_call("load_skill", skill_id="../../etc/passwd"))

    assert out.status == "error"


@pytest.mark.asyncio
async def test_bodies_are_loaded_once_per_run(monkeypatch):
    """_build_system_prompt and _build_tools both need the decision; the query
    must not run twice."""
    runner = _runner(monkeypatch, {101: _big(SKILL_INLINE_MAX_TOKENS + 1)})

    await runner._build_system_prompt()
    await runner._build_tools()
    await runner._dispatch(_call("load_skill", skill_id=101))

    runner._load_skill_bodies.assert_awaited_once()
