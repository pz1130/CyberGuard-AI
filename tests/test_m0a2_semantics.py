"""M0a-2 semantic changes: schema validate, is_error, sequential, tokens, constraints."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_core.compressor import (
    SUMMARY_PROMPT,
    compress_history,
    ensure_constraints_in_summary,
    select_window,
)
from agent_core.pipeline import run_tool_call
from agent_core.run_loop import RunLoopConfig, run_loop
from agent_core.schema_validate import SchemaValidationError, validate_tool_arguments
from agent_core.tokens import estimate_text_tokens, estimate_tokens, remaining_budget
from agent_core.tool_result import ToolResult, normalize_tool_result


SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "string"},
        "ports": {"type": "string"},
        "n": {"type": "integer"},
    },
    "required": ["target"],
}


def test_validate_tool_arguments_rejects_unknown_and_missing():
    with pytest.raises(SchemaValidationError, match="unknown"):
        validate_tool_arguments({"bogus": "x"}, SCHEMA)
    with pytest.raises(SchemaValidationError, match="missing required"):
        validate_tool_arguments({"ports": "80"}, SCHEMA)


def test_validate_tool_arguments_type_and_enum():
    schema = {
        "properties": {"mode": {"enum": ["a", "b"]}, "n": {"type": "integer"}},
        "required": [],
    }
    with pytest.raises(SchemaValidationError, match="enum"):
        validate_tool_arguments({"mode": "c"}, schema)
    with pytest.raises(SchemaValidationError, match="integer"):
        validate_tool_arguments({"n": "abc"}, schema)
    assert validate_tool_arguments({"n": "42", "mode": "a"}, schema)["n"] == "42"


@pytest.mark.asyncio
async def test_pipeline_validate_blocks_execute():
    executed = False

    async def execute(ctx, args):
        nonlocal executed
        executed = True
        return {"status": "completed"}

    out = await run_tool_call(
        tool_name="scan",
        arguments={"bogus": 1},
        execute=execute,
        metadata={"input_schema": SCHEMA},
    )
    assert out["status"] == "error" and out["is_error"] is True
    assert "unknown" in out["error"]
    assert executed is False


def test_normalize_tool_result_error_substring_not_is_error():
    # INV-32: payload containing "ERROR" text is not automatically an error
    tr = normalize_tool_result("Found ERROR in log line 12")
    assert tr.is_error is False
    assert "ERROR" in tr.content


def test_normalize_tool_result_structured_status():
    tr = normalize_tool_result({"status": "completed", "stdout": "ERROR: in output"})
    assert tr.is_error is False
    assert tr.content == "ERROR: in output"
    tr2 = normalize_tool_result({"status": "error", "error": "boom"})
    assert tr2.is_error is True


def test_normalize_tool_result_explicit_is_error():
    tr = normalize_tool_result(ToolResult(content="ok", is_error=False))
    assert tr.is_error is False


def test_cjk_token_estimate_higher_than_ascii_heuristic():
    # Equal character counts: CJK ≈ 1 tok/char, ASCII ≈ 0.25
    cjk = estimate_text_tokens("威胁" * 40)       # 80 CJK chars → 80
    ascii_ = estimate_text_tokens("ab" * 40)      # 80 ASCII → 20
    assert cjk == 80 and ascii_ == 20
    assert cjk > ascii_ * 3


def test_remaining_budget():
    assert remaining_budget(8192, reserve_output=1024, reserve_system=512) == 8192 - 1024 - 512


def test_select_window_preserves_current_turn():
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    # current turn starts at index 8 (last user); keep_last=2
    out = select_window(msgs, "sum", keep_last=2, preserve_turn_from=8)
    # turn = m8,m9 (2) → need 0 older → tail length 2
    assert [m["content"] for m in out[1:]] == ["m8", "m9"]
    # long turn
    out2 = select_window(msgs, "sum", keep_last=2, preserve_turn_from=5)
    assert [m["content"] for m in out2[1:]] == ["m5", "m6", "m7", "m8", "m9"]


def test_ensure_constraints_appended_when_missing():
    s = ensure_constraints_in_summary(
        "## Goal\nhi",
        {"authorization": "read-only", "sandbox_mode": "seatbelt"},
    )
    assert "## Constraints" in s
    assert "read-only" in s and "seatbelt" in s


def test_summary_prompt_has_six_sections():
    for h in (
        "## Goal",
        "## Constraints",
        "## Progress",
        "## Key Decisions",
        "## Next Steps",
        "## Critical Context",
    ):
        assert h in SUMMARY_PROMPT


@pytest.mark.asyncio
async def test_compress_history_injects_constraints_into_prompt():
    history = [{"role": "user", "content": "x" * 2000}]
    router = AsyncMock()
    router.chat = AsyncMock(
        return_value=(
            "## Goal\nx\n## Constraints\ny\n## Progress\n"
            "## Key Decisions\n## Next Steps\n## Critical Context\n"
        )
    )
    await compress_history(
        history,
        router,
        max_tokens=10,
        keep_last=1,
        constraints={"authorization": "read-only", "sandbox_mode": "none"},
    )
    user_msg = router.chat.await_args.kwargs["messages"][1]["content"]
    assert "read-only" in user_msg and "sandbox_mode" in user_msg


@pytest.mark.asyncio
async def test_run_loop_default_sequential_order():
    """Two tools must run one after another (default sequential)."""
    order = []
    calls = [
        SimpleNamespace(id="1", function=SimpleNamespace(name="a", arguments="{}")),
        SimpleNamespace(id="2", function=SimpleNamespace(name="b", arguments="{}")),
    ]
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            return SimpleNamespace(content="", tool_calls=calls)
        return "done"

    async def dispatch(call):
        order.append(call.function.name + ":start")
        await asyncio.sleep(0.01)
        order.append(call.function.name + ":end")
        return f"ok-{call.function.name}"

    events = []
    async for ev in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(max_steps=5, tool_call_budget=10, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    # sequential: a fully finishes before b starts
    assert order == ["a:start", "a:end", "b:start", "b:end"]
    ends = [e for e in events if e["type"] == "tool_call_end"]
    assert ends[0]["error"] is False


@pytest.mark.asyncio
async def test_run_loop_parallel_when_all_opt_in():
    order = []
    calls = [
        SimpleNamespace(id="1", function=SimpleNamespace(name="a", arguments="{}")),
        SimpleNamespace(id="2", function=SimpleNamespace(name="b", arguments="{}")),
    ]
    step = {"n": 0}
    gate = asyncio.Event()

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            return SimpleNamespace(content="", tool_calls=calls)
        return "done"

    async def dispatch(call):
        order.append(call.function.name + ":start")
        if call.function.name == "a":
            await gate.wait()
        else:
            gate.set()
        order.append(call.function.name + ":end")
        return "ok"

    async for _ in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(max_steps=5, tool_call_budget=10, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
        execution_mode_for=lambda c: "parallel",
    ):
        pass

    # both started before either finished (parallel)
    assert order.index("a:start") < order.index("a:end")
    assert order.index("b:start") < order.index("a:end")


@pytest.mark.asyncio
async def test_run_loop_is_error_not_from_error_substring():
    call = SimpleNamespace(
        id="1", function=SimpleNamespace(name="t", arguments="{}")
    )
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            return SimpleNamespace(content="", tool_calls=[call])
        return "done"

    async def dispatch(call):
        return "scan found ERROR in banner"

    events = []
    async for ev in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(max_steps=5, tool_call_budget=5, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
    ):
        events.append(ev)

    end = next(e for e in events if e["type"] == "tool_call_end")
    assert end["error"] is False
