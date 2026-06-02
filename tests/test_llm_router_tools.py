import os
import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("MOCK_MODE", "true")  # avoid real network

from app.services import llm_router as llm_router_module


@pytest.mark.asyncio
async def test_chat_returns_message_when_tools_passed(monkeypatch):
    router = llm_router_module.LLMRouter()

    # Fake AsyncOpenAI client whose chat.completions.create returns a message
    # with tool_calls set.
    fake_msg = MagicMock()
    fake_msg.content = None
    fake_msg.tool_calls = [MagicMock(id="call_1")]
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="tool_calls")]
    fake_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())

    # MOCK_MODE branch must be bypassed for this test
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    msg = await router.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "x"}}],
    )
    assert msg.tool_calls and msg.tool_calls[0].id == "call_1"


@pytest.mark.asyncio
async def test_chat_returns_string_when_no_tools(monkeypatch):
    """Backward-compat: tools=None or tools=[] returns a plain string."""
    router = llm_router_module.LLMRouter()

    fake_msg = MagicMock()
    fake_msg.content = "plain text reply"
    fake_msg.tool_calls = None
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="stop")]
    fake_resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    # tools=None
    out = await router.chat([{"role": "user", "content": "hi"}])
    assert isinstance(out, str) and out == "plain text reply"

    # tools=[] — should behave the same
    out_empty = await router.chat([{"role": "user", "content": "hi"}], tools=[])
    assert isinstance(out_empty, str) and out_empty == "plain text reply"


@pytest.mark.asyncio
async def test_chat_records_langfuse_generation(monkeypatch):
    """When a trace_run is active and Langfuse is configured, chat records one
    generation carrying the call's input/output."""
    import app.core.langfuse_tracing as lf
    router = llm_router_module.LLMRouter()

    fake_msg = MagicMock()
    fake_msg.content = "the answer"
    fake_msg.tool_calls = None
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="stop")]
    fake_resp.usage = MagicMock(prompt_tokens=4, completion_tokens=6, total_tokens=10)

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    lf_client = MagicMock()
    monkeypatch.setattr(lf, "_client", lf_client)

    with lf.trace_run(session_id="conv-9", agent_name="osint", user_id=3):
        out = await router.chat([{"role": "user", "content": "hi"}])

    assert out == "the answer"
    gen = lf_client.trace.return_value.generation
    gen.assert_called_once()
    kwargs = gen.call_args.kwargs
    assert kwargs["output"] == "the answer"
    assert kwargs["input"] == [{"role": "user", "content": "hi"}]
    assert kwargs["usage"] == {"input": 4, "output": 6, "total": 10}
