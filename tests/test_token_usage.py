"""Token usage recording and pricing tests."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.token_usage import (
    calculate_cost,
    get_configured_model_price,
    get_token_usage_summary,
)
from app.services import llm_router as llm_router_module
from app.services.token_usage_service import TokenUsageService


class FakeStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_record_usage_inserts_one_row_per_call():
    db = MagicMock()
    db.commit = AsyncMock()

    await TokenUsageService.record_usage(
        db=db,
        provider_id=7,
        provider_name="Example",
        model_name="model-a",
        prompt_tokens=11,
        completion_tokens=5,
        total_tokens=16,
    )

    row = db.add.call_args.args[0]
    assert row.provider_id == "7"
    assert row.model_name == "model-a"
    assert row.prompt_tokens == 11
    assert row.completion_tokens == 5
    assert row.total_tokens == 16
    assert row.call_count == 1
    db.commit.assert_awaited_once()


def test_cost_uses_exact_configured_model_price():
    provider = SimpleNamespace(models=[{
        "name": "model-a",
        "input_price_per_million": 2.0,
        "output_price_per_million": 6.0,
    }])

    assert get_configured_model_price(provider, "model-a") == (2.0, 6.0)
    assert get_configured_model_price(provider, "model-b") is None
    assert calculate_cost(1_000_000, 500_000, 2.0, 6.0) == 5.0


@pytest.mark.asyncio
async def test_summary_separates_priced_and_unpriced_tokens():
    logs = [
        SimpleNamespace(
            provider_id="7", provider_name="Example", model_name="priced",
            prompt_tokens=1_000_000, completion_tokens=500_000,
            total_tokens=1_500_000, call_count=2, date_str="2026-09-12",
        ),
        SimpleNamespace(
            provider_id="7", provider_name="Example", model_name="unpriced",
            prompt_tokens=100, completion_tokens=20,
            total_tokens=120, call_count=1, date_str="2026-09-12",
        ),
    ]
    provider = SimpleNamespace(id=7, models=[{
        "name": "priced",
        "input_price_per_million": 2.0,
        "output_price_per_million": 6.0,
    }])

    def result(items):
        scalars = MagicMock()
        scalars.all.return_value = items
        value = MagicMock()
        value.scalars.return_value = scalars
        return value

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(logs), result([provider])])

    summary = await get_token_usage_summary(
        start_date="2026-09-01",
        end_date="2026-09-30",
        model_name=None,
        provider_id=None,
        db=db,
        current_user=SimpleNamespace(),
    )

    assert summary.total_tokens == 1_500_120
    assert summary.total_calls == 3
    assert summary.total_cost_usd == 5.0
    assert summary.priced_tokens == 1_500_000
    assert summary.unpriced_tokens == 120
    costs = {item.model_name: item.estimated_cost_usd for item in summary.by_model}
    assert costs == {"priced": 5.0, "unpriced": None}


@pytest.mark.asyncio
async def test_stream_chat_records_provider_reported_usage(monkeypatch):
    router = llm_router_module.LLMRouter()
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=4, total_tokens=16)
    content_chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))],
        usage=None,
    )
    usage_chunk = SimpleNamespace(choices=[], usage=usage)
    create = AsyncMock(return_value=FakeStream([content_chunk, usage_chunk]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_provider_rpm", AsyncMock(return_value=60))
    monkeypatch.setattr(llm_router_module, "rate_limit", AsyncMock())
    monkeypatch.setattr(llm_router_module, "_record_generation", MagicMock())
    record = AsyncMock()
    monkeypatch.setattr(router, "_record_token_usage", record)

    chunks = [chunk async for chunk in router.stream_chat(
        [{"role": "user", "content": "hi"}],
        model="model-a",
        provider_id=7,
    )]

    assert chunks == ["hello"]
    assert create.await_args.kwargs["stream_options"] == {"include_usage": True}
    record.assert_awaited_once_with("model-a", 7, usage_chunk)


@pytest.mark.asyncio
async def test_stream_chat_retries_when_provider_rejects_usage_option(monkeypatch):
    class UnsupportedStreamOption(Exception):
        status_code = 400

    router = llm_router_module.LLMRouter()
    content_chunk = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="compatible"))],
        usage=None,
    )
    create = AsyncMock(side_effect=[
        UnsupportedStreamOption("unknown stream_options"),
        FakeStream([content_chunk]),
    ])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    async def call_once(operation, label):
        return await operation()

    monkeypatch.setattr(llm_router_module.settings, "MOCK_MODE", False)
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=client))
    monkeypatch.setattr(router, "_load_master_config", AsyncMock(return_value={}))
    monkeypatch.setattr(router, "_provider_rpm", AsyncMock(return_value=60))
    monkeypatch.setattr(llm_router_module, "rate_limit", AsyncMock())
    monkeypatch.setattr(llm_router_module, "acall_with_retry", call_once)
    monkeypatch.setattr(llm_router_module, "_record_generation", MagicMock())
    record = AsyncMock()
    monkeypatch.setattr(router, "_record_token_usage", record)

    chunks = [chunk async for chunk in router.stream_chat(
        [{"role": "user", "content": "hi"}],
        model="model-a",
        provider_id=7,
    )]

    assert chunks == ["compatible"]
    assert create.await_count == 2
    assert "stream_options" in create.await_args_list[0].kwargs
    assert "stream_options" not in create.await_args_list[1].kwargs
    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_embed_records_provider_reported_usage(monkeypatch):
    router = llm_router_module.LLMRouter()
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=0, total_tokens=3),
    )
    client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(return_value=response))
    )
    monkeypatch.setattr(router, "get_client_async", AsyncMock(return_value=client))
    record = AsyncMock()
    monkeypatch.setattr(router, "_record_token_usage", record)

    vectors = await router.embed(["hello"], model="embed-a", provider_id=7)

    assert vectors == [[0.1, 0.2]]
    record.assert_awaited_once_with("embed-a", 7, response)
