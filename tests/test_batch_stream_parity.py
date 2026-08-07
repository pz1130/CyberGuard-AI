"""Batch and streaming runs must agree, and must cost the same.

The streaming path used to re-generate the final answer with a second,
tool-less `stream_chat` request once the loop finished. That was an extra
full-context call, and nothing forced its text to match what the batch path had
already produced for the identical run.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner


def _tc(cid, name):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments="{}"))


def _scripted_router(turns):
    """A router whose stream_chat_events replays `turns`, counting requests."""
    remaining = list(turns)
    calls = {"n": 0}

    async def fake_events(*args, **kwargs):
        calls["n"] += 1
        for ev in remaining.pop(0):
            yield ev

    return SimpleNamespace(stream_chat_events=fake_events), calls


def _runner(monkeypatch, turns, **overrides):
    router, calls = _scripted_router(turns)
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: router)
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 6, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium"}
    cfg.update(overrides)
    r = InternalAgentRunner(cfg)
    monkeypatch.setattr(r, "_build_tools", AsyncMock(return_value=[{"type": "function"}]))
    monkeypatch.setattr(r, "_dispatch", AsyncMock(return_value="tool ok"))
    return r, calls


# One tool turn, then a text answer delivered in three fragments.
_TURNS = [
    [{"type": "done", "content": "", "tool_calls": [_tc("c1", "grep")],
      "finish_reason": "tool_calls"}],
    [{"type": "text", "delta": "the "}, {"type": "text", "delta": "final "},
     {"type": "text", "delta": "answer"},
     {"type": "done", "content": "the final answer", "tool_calls": None,
      "finish_reason": "stop"}],
]


@pytest.mark.asyncio
async def test_batch_and_stream_produce_identical_output(monkeypatch):
    batch_runner, _ = _runner(monkeypatch, [list(t) for t in _TURNS])
    batch = await batch_runner.execute(task="go", conversation_id=None, user_id=1)

    stream_runner, _ = _runner(monkeypatch, [list(t) for t in _TURNS])
    events = [ev async for ev in stream_runner.execute_stream("go", None, 1)]

    assert batch["status"] == "completed"
    assert events[-1]["type"] == "done"
    assert events[-1]["output"] == batch["output"] == "the final answer"


@pytest.mark.asyncio
async def test_streaming_costs_the_same_number_of_llm_calls_as_batch(monkeypatch):
    batch_runner, batch_calls = _runner(monkeypatch, [list(t) for t in _TURNS])
    await batch_runner.execute(task="go", conversation_id=None, user_id=1)

    stream_runner, stream_calls = _runner(monkeypatch, [list(t) for t in _TURNS])
    _ = [ev async for ev in stream_runner.execute_stream("go", None, 1)]

    assert stream_calls["n"] == batch_calls["n"] == 2   # was 3 on the stream path


@pytest.mark.asyncio
async def test_deltas_reach_the_consumer_and_join_to_the_final_text(monkeypatch):
    runner, _ = _runner(monkeypatch, [list(t) for t in _TURNS])
    events = [ev async for ev in runner.execute_stream("go", None, 1)]

    deltas = [e["content"] for e in events if e["type"] == "text"]
    assert deltas == ["the ", "final ", "answer"]
    assert "".join(deltas) == events[-1]["output"]


@pytest.mark.asyncio
async def test_tool_call_events_still_surface_around_the_text(monkeypatch):
    runner, _ = _runner(monkeypatch, [list(t) for t in _TURNS])
    types = [e["type"] async for e in runner.execute_stream("go", None, 1)]

    assert types[0] == "start"
    assert types.index("tool_call_start") < types.index("text")
    assert types[-1] == "done"


# ---- fallback for routers without event streaming ---------------------------

@pytest.mark.asyncio
async def test_router_without_event_streaming_falls_back_to_chat(monkeypatch):
    """Older providers and test doubles keep working; only the final answer
    arrives in one piece instead of token by token."""
    router = SimpleNamespace(chat=AsyncMock(side_effect=[
        SimpleNamespace(content="", tool_calls=[_tc("c1", "grep")]),
        SimpleNamespace(content="one-shot answer", tool_calls=None),
    ]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: router)

    runner = InternalAgentRunner(
        {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
         "llm_model": "m", "tool_loop_max_steps": 6, "memory_window": 0,
         "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
         "permission_level": "medium"})
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[{"type": "function"}]))
    monkeypatch.setattr(runner, "_dispatch", AsyncMock(return_value="tool ok"))

    events = [ev async for ev in runner.execute_stream("go", None, 1)]

    assert events[-1]["output"] == "one-shot answer"
    assert router.chat.await_count == 2
    assert not [e for e in events if e["type"] == "text"]


# ---- mid-stream failures ----------------------------------------------------

@pytest.mark.asyncio
async def test_failure_after_deltas_is_not_retried(monkeypatch):
    """Replaying a turn that already emitted text would show the user the same
    prefix twice."""
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        yield {"type": "text", "delta": "partial"}
        yield {"type": "error", "error": "connection reset"}

    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(stream_chat_events=flaky))
    runner = InternalAgentRunner(
        {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
         "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
         "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
         "permission_level": "medium"})
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[]))

    events = [ev async for ev in runner.execute_stream("go", None, 1)]

    assert calls["n"] == 1                       # no replay
    assert events[-1]["type"] == "error"
    assert [e["content"] for e in events if e["type"] == "text"] == ["partial"]


@pytest.mark.asyncio
async def test_failure_before_any_delta_is_still_retried(monkeypatch):
    """The existing self-recovery behaviour is preserved when nothing was sent."""
    from app.services.internal_agent import LLM_RETRY_MAX
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= LLM_RETRY_MAX:
            yield {"type": "error", "error": "handshake failed"}
            return
        yield {"type": "done", "content": "recovered", "tool_calls": None,
               "finish_reason": "stop"}

    monkeypatch.setattr(ia_mod, "get_llm_router",
                        lambda: SimpleNamespace(stream_chat_events=flaky))
    runner = InternalAgentRunner(
        {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
         "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
         "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
         "permission_level": "medium"})
    monkeypatch.setattr(runner, "_build_tools", AsyncMock(return_value=[]))

    res = await runner.execute(task="go", conversation_id=None, user_id=1)

    assert calls["n"] == LLM_RETRY_MAX + 1
    assert res["output"] == "recovered"
