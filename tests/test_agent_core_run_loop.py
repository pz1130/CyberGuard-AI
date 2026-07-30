"""M0a-1: agent_core run_loop / loop_utils / compact behavior."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_core.compact import maybe_compact_messages
from agent_core.loop_utils import (
    LOOP_DETECT_THRESHOLD,
    REFLECT_MAX,
    TOOL_RESULT_MAX_CHARS,
    estimate_message_chars,
    tool_call_fingerprint,
    truncate_tool_result,
)
from agent_core.run_loop import RunLoopConfig, run_loop


def test_fingerprint_order_invariant():
    a = tool_call_fingerprint("t", '{"b":1,"a":2}')
    b = tool_call_fingerprint("t", '{"a":2,"b":1}')
    assert a == b


def test_truncate_tool_result_caps():
    short = "x" * 10
    assert truncate_tool_result(short) == short
    big = "y" * (TOOL_RESULT_MAX_CHARS + 50)
    out = truncate_tool_result(big)
    assert len(out) < len(big)
    assert "truncated" in out


@pytest.mark.asyncio
async def test_run_loop_text_only_answer():
    async def chat(*, messages, tools=None):
        return "final answer"

    async def dispatch(call):
        raise AssertionError("should not dispatch")

    events = []
    async for ev in run_loop(
        task="hi",
        system_prompt="sys",
        history=[],
        tools=None,
        config=RunLoopConfig(max_steps=3, tool_call_budget=5, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "answer_ready" in types
    ready = next(e for e in events if e["type"] == "answer_ready")
    assert ready["candidate_text"] == "final answer"


@pytest.mark.asyncio
async def test_run_loop_one_tool_then_answer():
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            call = SimpleNamespace(
                id="c1",
                function=SimpleNamespace(name="echo", arguments='{"x":1}'),
            )
            return SimpleNamespace(content="", tool_calls=[call])
        return "done"

    async def dispatch(call):
        return "tool-out"

    events = []
    async for ev in run_loop(
        task="do",
        system_prompt="sys",
        history=[],
        tools=[{"type": "function", "function": {"name": "echo"}}],
        config=RunLoopConfig(max_steps=5, tool_call_budget=10, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert "tool_call_start" in types and "tool_call_end" in types
    assert "answer_ready" in types


@pytest.mark.asyncio
async def test_run_loop_loop_detection_aborts():
    """Same tool+args repeated past threshold → reflector → abort."""
    call = SimpleNamespace(
        id="c1",
        function=SimpleNamespace(name="spin", arguments='{"a":1}'),
    )

    async def chat(*, messages, tools=None):
        return SimpleNamespace(content="", tool_calls=[call])

    dispatched = 0

    async def dispatch(call):
        nonlocal dispatched
        dispatched += 1
        return "same"

    events = []
    async for ev in run_loop(
        task="loop",
        system_prompt="sys",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(
            max_steps=20,
            tool_call_budget=50,
            agent_name="t",
            loop_detect_threshold=LOOP_DETECT_THRESHOLD,
            reflect_max=REFLECT_MAX,
        ),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    assert any(e["type"] == "error" and "stuck" in e.get("error", "") for e in events)
    # First LOOP_DETECT_THRESHOLD-1 calls actually dispatch; rest are notices.
    assert dispatched == LOOP_DETECT_THRESHOLD - 1


@pytest.mark.asyncio
async def test_run_loop_emits_audit_agent_and_turn():
    from agent_core.events import AuditBus, AuditLayer, AuditPhase

    bus = AuditBus()
    seen = []

    async def sub(ev):
        seen.append((ev.layer, ev.phase, ev.name))

    bus.subscribe(sub)

    async def chat(*, messages, tools=None):
        return "ok"

    async def dispatch(call):
        raise AssertionError("no tools")

    async for _ in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=None,
        config=RunLoopConfig(max_steps=2, tool_call_budget=5, agent_name="a1"),
        chat=chat,
        dispatch=dispatch,
        audit_bus=bus,
    ):
        pass

    layers = [s[0] for s in seen]
    assert AuditLayer.AGENT in layers
    assert AuditLayer.TURN in layers
    # agent start then end (finally)
    assert seen[0][0] is AuditLayer.AGENT and seen[0][1] is AuditPhase.START
    assert seen[-1][0] is AuditLayer.AGENT and seen[-1][1] is AuditPhase.END


@pytest.mark.asyncio
async def test_audit_emit_failure_aborts_turn():
    """INV-29: subscriber errors must propagate (not swallowed)."""
    from agent_core.events import AuditBus

    bus = AuditBus()

    async def bad(ev):
        raise RuntimeError("audit disk full")

    bus.subscribe(bad)

    async def chat(*, messages, tools=None):
        return "x"

    async def dispatch(call):
        return "y"

    with pytest.raises(RuntimeError, match="audit disk full"):
        async for _ in run_loop(
            task="t",
            system_prompt="s",
            history=[],
            tools=None,
            config=RunLoopConfig(max_steps=1, tool_call_budget=1, agent_name="a"),
            chat=chat,
            dispatch=dispatch,
            audit_bus=bus,
        ):
            pass


@pytest.mark.asyncio
async def test_pipeline_emits_tool_execution_events():
    from agent_core.events import AuditBus, AuditLayer, AuditPhase
    from agent_core.pipeline import run_tool_call

    bus = AuditBus()
    seen = []

    async def sub(ev):
        seen.append((ev.layer, ev.phase, ev.name))

    bus.subscribe(sub)

    async def execute(ctx, args):
        return {"status": "completed"}

    out = await run_tool_call(
        tool_name="nmap",
        arguments={"t": "1"},
        execute=execute,
        audit_bus=bus,
    )
    assert out["status"] == "completed"
    assert (AuditLayer.TOOL_EXECUTION, AuditPhase.START, "nmap") in seen
    assert (AuditLayer.TOOL_EXECUTION, AuditPhase.END, "nmap") in seen


@pytest.mark.asyncio
async def test_maybe_compact_messages_summarizes():
    messages = [{"role": "system", "content": "sys"}]
    for i in range(20):
        messages.append({"role": "user", "content": ("payload " + str(i) + " ") * 200})

    chat = AsyncMock(return_value="SUMMARY TEXT")
    out = await maybe_compact_messages(
        messages, chat, compact_chars=100, keep_recent=3
    )
    assert out[0]["role"] == "system"
    assert any("对话摘要" in (m.get("content") or "") for m in out)
    assert estimate_message_chars(out) < estimate_message_chars(messages)
    chat.assert_awaited()
