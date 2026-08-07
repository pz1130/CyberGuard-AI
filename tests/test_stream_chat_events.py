"""Streamed tool-call accumulation in LLMRouter.stream_chat_events.

Providers deliver tool calls in fragments: the id arrives once, the function
name may be split, and the JSON arguments arrive a few characters at a time
across many chunks. Getting the reassembly wrong is how a scan ends up running
with half its arguments.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import llm_router as lr_mod
from app.services.llm_router import LLMRouter


def _delta(content=None, tool_calls=None, finish_reason=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content, tool_calls=tool_calls),
            finish_reason=finish_reason)],
        usage=None)


def _tc_delta(index, *, id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index, id=id,
        function=SimpleNamespace(name=name, arguments=arguments))


def _router_with_stream(chunks):
    router = LLMRouter.__new__(LLMRouter)

    async def chunk_stream():
        for c in chunks:
            yield c

    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: chunk_stream())))

    router.get_client_async = AsyncMock(return_value=client)
    router.get_provider_config_async = AsyncMock(return_value=None)
    router._load_master_config = AsyncMock(return_value={"temperature": 0.3})
    router._guard_messages = lambda m, p=None: m
    router._strip_think_blocks = lambda t: t
    router._record_token_usage = AsyncMock()
    router._provider_rpm = AsyncMock(return_value=None)
    return router


async def _collect(router, **kwargs):
    return [ev async for ev in router.stream_chat_events(
        messages=[{"role": "user", "content": "hi"}], model="m", **kwargs)]


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    monkeypatch.setattr(lr_mod.settings, "MOCK_MODE", False)
    monkeypatch.setattr(lr_mod, "rate_limit", AsyncMock())
    monkeypatch.setattr(lr_mod, "_record_generation", lambda *a, **kw: None)
    monkeypatch.setattr(lr_mod, "acall_with_retry",
                        AsyncMock(side_effect=lambda fn, label=None: fn()))


@pytest.mark.asyncio
async def test_text_deltas_stream_then_join():
    router = _router_with_stream([
        _delta(content="Hel"), _delta(content="lo"),
        _delta(finish_reason="stop"),
    ])
    events = await _collect(router)

    assert [e["delta"] for e in events if e["type"] == "text"] == ["Hel", "lo"]
    done = events[-1]
    assert done["content"] == "Hello"
    assert done["tool_calls"] is None
    assert done["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_tool_call_fragments_are_reassembled_in_order():
    router = _router_with_stream([
        _delta(tool_calls=[_tc_delta(0, id="call_1", name="nmap_", arguments='{"tar')]),
        _delta(tool_calls=[_tc_delta(0, name="scan", arguments='get": "10.0')]),
        _delta(tool_calls=[_tc_delta(0, arguments='.0.0/8", "ports": "1-65535"}')]),
        _delta(finish_reason="tool_calls"),
    ])
    events = await _collect(router, tools=[{"type": "function"}])

    calls = events[-1]["tool_calls"]
    assert len(calls) == 1
    assert calls[0].id == "call_1"
    assert calls[0].function.name == "nmap_scan"
    assert calls[0].function.arguments == (
        '{"target": "10.0.0.0/8", "ports": "1-65535"}')


@pytest.mark.asyncio
async def test_parallel_tool_calls_stay_separated_and_ordered():
    router = _router_with_stream([
        _delta(tool_calls=[_tc_delta(0, id="a", name="grep", arguments='{"q":')]),
        _delta(tool_calls=[_tc_delta(1, id="b", name="ls", arguments='{"p":')]),
        _delta(tool_calls=[_tc_delta(1, arguments='"/tmp"}')]),
        _delta(tool_calls=[_tc_delta(0, arguments='"err"}')]),
        _delta(finish_reason="tool_calls"),
    ])
    events = await _collect(router, tools=[{"type": "function"}])

    calls = events[-1]["tool_calls"]
    assert [c.id for c in calls] == ["a", "b"]          # ordered by index
    assert calls[0].function.arguments == '{"q":"err"}'
    assert calls[1].function.arguments == '{"p":"/tmp"}'


@pytest.mark.asyncio
async def test_length_finish_reason_is_forwarded():
    """The loop refuses to execute tool calls from a truncated response, so this
    has to survive the streaming path too."""
    router = _router_with_stream([
        _delta(tool_calls=[_tc_delta(0, id="a", name="scan", arguments='{"target"')]),
        _delta(finish_reason="length"),
    ])
    events = await _collect(router, tools=[{"type": "function"}])
    assert events[-1]["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_text_and_tool_calls_in_the_same_turn():
    router = _router_with_stream([
        _delta(content="Let me check. "),
        _delta(tool_calls=[_tc_delta(0, id="a", name="grep", arguments="{}")]),
        _delta(finish_reason="tool_calls"),
    ])
    events = await _collect(router, tools=[{"type": "function"}])

    assert [e["delta"] for e in events if e["type"] == "text"] == ["Let me check. "]
    assert events[-1]["content"] == "Let me check. "
    assert len(events[-1]["tool_calls"]) == 1


@pytest.mark.asyncio
async def test_chunks_without_choices_are_skipped():
    """Usage-only trailer chunks carry no choices."""
    router = _router_with_stream([
        _delta(content="ok"),
        SimpleNamespace(choices=[], usage=SimpleNamespace(total_tokens=7)),
        _delta(finish_reason="stop"),
    ])
    events = await _collect(router)
    assert events[-1]["content"] == "ok"
    router._record_token_usage.assert_awaited()


@pytest.mark.asyncio
async def test_provider_failure_yields_an_error_event():
    router = _router_with_stream([])
    router.get_client_async = AsyncMock(side_effect=RuntimeError("no provider"))

    events = await _collect(router)
    assert events == [{"type": "error", "error": "no provider"}]
