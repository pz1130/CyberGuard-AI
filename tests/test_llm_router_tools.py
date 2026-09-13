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
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": 1, "model": "test-model",
    }))
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={}))
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
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": 1, "model": "test-model",
    }))
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={}))
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
async def test_chat_uses_master_provider_and_exact_model(monkeypatch):
    router = llm_router_module.LLMRouter()
    fake_msg = MagicMock(content="reply", tool_calls=None)
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="stop")]
    fake_resp.usage = None
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    get_client = AsyncMock(return_value=fake_client)

    monkeypatch.setattr(router, "get_client_async", get_client)
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": 42,
        "model": "Case-Sensitive-Model",
    }))
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={
        "provider_type": "openai",
        "models": [{"name": "Case-Sensitive-Model"}],
    }))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    assert await router.chat([{"role": "user", "content": "hi"}]) == "reply"
    get_client.assert_awaited_once_with(provider_id=42)
    assert fake_client.chat.completions.create.await_args.kwargs["model"] == "Case-Sensitive-Model"


def test_auto_uses_the_master_provider_model_pair():
    from app.services.llm_router import bound_provider_model

    assert bound_provider_model(
        master_config={"provider_id": 34, "model": "MiniMax-M3"},
    ) == (34, "MiniMax-M3")


def test_request_pair_wins_over_master_pair():
    from app.services.llm_router import bound_provider_model

    assert bound_provider_model(
        provider_id=8,
        model="model-b",
        master_config={"provider_id": 34, "model": "MiniMax-M3"},
    ) == (8, "model-b")


def test_unbound_master_model_is_not_paired_with_another_provider():
    from app.services.llm_router import UnboundSelectionError, bound_provider_model

    with pytest.raises(UnboundSelectionError, match="bound Provider"):
        bound_provider_model(master_config={"provider_id": None, "model": "MiniMax-m2.7"})


def test_partial_request_selection_is_rejected_even_when_master_is_bound():
    from app.services.llm_router import UnboundSelectionError, bound_provider_model

    master = {"provider_id": 34, "model": "MiniMax-M3"}
    with pytest.raises(UnboundSelectionError, match="together"):
        bound_provider_model(provider_id=8, master_config=master)
    with pytest.raises(UnboundSelectionError, match="together"):
        bound_provider_model(model="only-a-name", master_config=master)


@pytest.mark.asyncio
async def test_chat_auto_does_not_call_first_available_provider(monkeypatch):
    """AUTO must not send MiniMax-m2.7 (or any unbound model) to the first DB provider."""
    router = llm_router_module.LLMRouter()
    fallback = AsyncMock(return_value={
        "api_key": "unexpected", "base_url": "https://example.com/v1", "models": ["other"],
    })
    get_client = AsyncMock()
    monkeypatch.setattr(router, "_get_first_active_provider", fallback)
    monkeypatch.setattr(router, "get_client_async", get_client)
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": None,
        "model": "MiniMax-m2.7",
    }))
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    with pytest.raises(llm_router_module.UnboundSelectionError, match="bound Provider"):
        await router.chat([{"role": "user", "content": "hi"}])
    fallback.assert_not_awaited()
    get_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_ignores_session_model_name_override(monkeypatch):
    """A model name without its Provider must not ride along with the Master pair."""
    router = llm_router_module.LLMRouter()
    fake_msg = MagicMock(content="reply", tool_calls=None)
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg, finish_reason="stop")]
    fake_resp.usage = None
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
    get_client = AsyncMock(return_value=fake_client)

    monkeypatch.setattr(router, "get_client_async", get_client)
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": 42,
        "model": "Master-Model",
    }))
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={
        "provider_type": "openai",
        "models": [{"name": "Master-Model"}],
    }))
    monkeypatch.setattr(router, "_should_strip_think", AsyncMock(return_value=False))
    monkeypatch.setattr(router, "_record_token_usage", AsyncMock())
    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)

    assert await router.chat(
        [{"role": "user", "content": "hi"}],
        model_override="Session-Only-Name",
    ) == "reply"
    get_client.assert_awaited_once_with(provider_id=42)
    assert fake_client.chat.completions.create.await_args.kwargs["model"] == "Master-Model"


@pytest.mark.asyncio
async def test_explicit_unconfigured_provider_does_not_fall_back(monkeypatch):
    router = llm_router_module.LLMRouter()
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value=None))
    fallback = AsyncMock(return_value={"api_key": "unexpected", "base_url": "https://example.com/v1"})
    monkeypatch.setattr(router, "_get_first_active_provider", fallback)

    with pytest.raises(RuntimeError, match="selected AI provider"):
        await router.get_client_async(provider_id=999)
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_provider_skips_empty_openai_placeholder(monkeypatch):
    router = llm_router_module.LLMRouter()
    router.providers = [{
        "name": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o"],
    }]
    monkeypatch.setattr(router, "_get_first_active_provider", AsyncMock(return_value={
        "name": "configured",
        "api_key": "configured-key",
        "base_url": "https://configured.example/v1",
        "models": ["configured-model"],
    }))
    client_factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(llm_router_module, "AsyncOpenAI", client_factory)

    await router.get_client_async()

    client_factory.assert_called_once_with(
        api_key="configured-key", base_url="https://configured.example/v1"
    )


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
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={
        "provider_id": 1, "model": "test-model",
    }))
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={}))
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
