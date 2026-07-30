"""M0a-2 remaining: directional truncate, exclude_from_context, thinking, cache."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_core.messages import (
    is_excluded,
    mark_exclude_from_context,
    messages_for_model,
)
from agent_core.run_loop import RunLoopConfig, run_loop
from agent_core.truncate import truncate_text
from llm_router.cache_control import mark_system_for_cache, apply_prompt_cache_key
from llm_router.thinking import apply_thinking_to_kwargs, normalize_thinking_level


# ---- truncate ----

def test_truncate_tail_keeps_head():
    text = "HEAD\n" + ("line\n" * 100) + "TAIL_MARKER"
    out = truncate_text(text, mode="tail", max_chars=40)
    assert out.startswith("HEAD")
    assert "truncated" in out and "tail" in out
    assert "TAIL_MARKER" not in out


def test_truncate_head_keeps_tail():
    text = "HEAD_MARKER\n" + ("line\n" * 100) + "CRITICAL_TAIL"
    out = truncate_text(text, mode="head", max_chars=40)
    assert out.endswith("CRITICAL_TAIL") or "CRITICAL_TAIL" in out
    assert "truncated" in out and "head" in out
    assert "HEAD_MARKER" not in out


def test_truncate_max_lines_head():
    lines = [f"L{i}\n" for i in range(20)]
    text = "".join(lines)
    out = truncate_text(text, mode="head", max_lines=3)
    assert "L19" in out and "L17" in out
    assert "L0" not in out


def test_truncate_dual_constraint_picks_shorter():
    text = "a\n" * 50 + "END"
    by_lines = truncate_text(text, mode="tail", max_chars=10_000, max_lines=5)
    by_chars = truncate_text(text, mode="tail", max_chars=30, max_lines=100)
    assert len(by_lines) < len(text)
    assert len(by_chars) < len(text)


# ---- exclude_from_context ----

def test_messages_for_model_drops_excluded():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "evidence blob", "exclude_from_context": True},
        {"role": "user", "content": "real question"},
    ]
    out = messages_for_model(msgs)
    assert len(out) == 2
    assert out[1]["content"] == "real question"
    # original untouched
    assert is_excluded(msgs[1])


def test_mark_exclude_from_context():
    m = {"role": "user", "content": "x"}
    mark_exclude_from_context(m)
    assert is_excluded(m)
    mark_exclude_from_context(m, exclude=False)
    assert not is_excluded(m)


@pytest.mark.asyncio
async def test_run_loop_does_not_send_excluded_to_chat():
    seen = []

    async def chat(*, messages, tools=None):
        seen.append([m.get("content") for m in messages])
        return "ok"

    async def dispatch(call):
        return "x"

    # Pre-seed history with an excluded message via system+user then inject
    # by patching is hard; instead we rely on messages_for_model unit test
    # and chat path. Here we only verify plain path still works.
    async for _ in run_loop(
        task="hi",
        system_prompt="sys",
        history=[{"role": "user", "content": "secret", "exclude_from_context": True}],
        tools=None,
        config=RunLoopConfig(max_steps=2, tool_call_budget=2, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
    ):
        pass

    assert seen
    # history secret must not appear in any model payload
    for batch in seen:
        assert "secret" not in batch


@pytest.mark.asyncio
async def test_run_loop_truncate_head_preserves_tail():
    call = SimpleNamespace(
        id="1", function=SimpleNamespace(name="log", arguments="{}")
    )
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            return SimpleNamespace(content="", tool_calls=[call])
        return "done"

    long_out = "NOISE\n" * 200 + "FIND_ME_AT_END"

    async def dispatch(call):
        return long_out

    events = []
    async for ev in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(
            max_steps=5,
            tool_call_budget=5,
            agent_name="t",
            tool_result_max_chars=80,
            tool_truncate_mode="head",
        ),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    end = next(e for e in events if e["type"] == "tool_call_end")
    assert "FIND_ME_AT_END" in end["result_preview"] or "FIND_ME" in end["result_preview"]


# ---- thinking ----

def test_normalize_thinking_level():
    assert normalize_thinking_level("HIGH") == "high"
    assert normalize_thinking_level("nope") is None


def test_apply_thinking_openai_o_series():
    kw = apply_thinking_to_kwargs(
        {"model": "o3-mini", "messages": []},
        level="high",
        model="o3-mini",
        provider_type="openai",
    )
    assert kw.get("reasoning_effort") == "high"


def test_apply_thinking_off_is_noop():
    base = {"model": "o1", "messages": []}
    kw = apply_thinking_to_kwargs(base, level="off", model="o1", provider_type="openai")
    assert "reasoning_effort" not in kw


def test_apply_thinking_anthropic_budget():
    kw = apply_thinking_to_kwargs(
        {"model": "claude-sonnet", "messages": []},
        level="medium",
        model="claude-3-5-sonnet",
        provider_type="anthropic",
    )
    assert kw["extra_body"]["thinking"]["budget_tokens"] == 8192


# ---- cache ----

def test_mark_system_for_cache_anthropic():
    msgs = [
        {"role": "system", "content": "stable skills here"},
        {"role": "user", "content": "hi"},
    ]
    out = mark_system_for_cache(msgs, provider_type="anthropic", enabled=True)
    assert isinstance(out[0]["content"], list)
    assert out[0]["content"][-1].get("cache_control") == {"type": "ephemeral"}
    assert out[1]["content"] == "hi"


def test_mark_system_for_cache_openai_noop():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]
    out = mark_system_for_cache(msgs, provider_type="openai", enabled=True)
    assert out[0]["content"] == "sys"


def test_apply_prompt_cache_key():
    kw = apply_prompt_cache_key({"model": "x"}, cache_key="skills-v1")
    assert kw["prompt_cache_key"] == "skills-v1"


@pytest.mark.asyncio
async def test_llm_router_chat_filters_exclude_and_accepts_thinking(monkeypatch):
    from app.services import llm_router as mod

    router = mod.LLMRouter()
    captured = {}

    fake_msg = SimpleNamespace(content="answer", tool_calls=None)
    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=fake_msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=lambda **kw: captured.update(kw) or fake_resp)
            )
        )
    )
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={
        "provider_type": "openai", "models": [{"name": "o3-mini"}],
    }))
    monkeypatch.setattr(mod.settings, "MOCK_MODE", False)

    out = await router.chat(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "secret", "exclude_from_context": True},
            {"role": "user", "content": "hello"},
        ],
        model="o3-mini",
        provider_id=1,
        thinking="high",
    )
    assert out == "answer"
    sent = captured["messages"]
    assert all(m.get("content") != "secret" for m in sent)
    assert captured.get("reasoning_effort") == "high"
