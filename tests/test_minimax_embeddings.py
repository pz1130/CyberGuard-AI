"""MiniMax native embeddings protocol — not OpenAI /embeddings compatible.

MiniMax chat is OpenAI-compatible (/v1/chat/completions). Its embedding API
uses `{texts, type}` and returns `{vectors, base_resp}` instead of
`{input}` / `{data[].embedding}`. Calling the OpenAI SDK against MiniMax
yields HTTP 400 "No embedding data received".
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from llm_router.minimax_embeddings import (
    DEFAULT_EMBED_MODEL,
    build_payload,
    embeddings_url,
    is_minimax_base_url,
    parse_embeddings_response,
    resolve_embed_model,
)


def test_detects_minimax_hosts():
    assert is_minimax_base_url("https://api.minimaxi.com/v1")
    assert is_minimax_base_url("https://api.minimax.io/v1")
    assert is_minimax_base_url("https://api.minimax.chat/v1")
    assert is_minimax_base_url("https://api.minimax.cn/v1")
    assert not is_minimax_base_url("https://api.openai.com/v1")
    assert not is_minimax_base_url("https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert not is_minimax_base_url(None)
    assert not is_minimax_base_url("")


def test_embeddings_url_appends_path_and_group_id():
    assert embeddings_url("https://api.minimaxi.com/v1") == (
        "https://api.minimaxi.com/v1/embeddings"
    )
    assert embeddings_url("https://api.minimaxi.com/v1/", group_id="123") == (
        "https://api.minimaxi.com/v1/embeddings?GroupId=123"
    )


def test_payload_uses_texts_and_type_not_openai_input():
    payload = build_payload(["hello", "world"], model="embo-01", embed_type="db")
    assert payload == {
        "model": "embo-01",
        "texts": ["hello", "world"],
        "type": "db",
    }
    assert "input" not in payload
    query = build_payload(["q"], model="embo-01", embed_type="query")
    assert query["type"] == "query"


def test_unknown_embed_type_defaults_to_db():
    payload = build_payload(["x"], model="embo-01", embed_type="nope")
    assert payload["type"] == "db"


def test_openai_embedding_model_names_remap_to_embo_01():
    assert resolve_embed_model(None) == DEFAULT_EMBED_MODEL
    assert resolve_embed_model("") == DEFAULT_EMBED_MODEL
    assert resolve_embed_model("text-embedding-3-small") == DEFAULT_EMBED_MODEL
    assert resolve_embed_model("text-embedding-3-large") == DEFAULT_EMBED_MODEL
    assert resolve_embed_model("embo-01") == "embo-01"


def test_parse_vectors_and_reject_base_resp_errors():
    vectors, tokens = parse_embeddings_response({
        "vectors": [[0.1, 0.2], [0.3, 0.4]],
        "total_tokens": 9,
        "base_resp": {"status_code": 0, "status_msg": "success"},
    })
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert tokens == 9

    with pytest.raises(ValueError, match="MiniMax embeddings failed"):
        parse_embeddings_response({
            "vectors": [],
            "base_resp": {"status_code": 1002, "status_msg": "invalid group"},
        })

    with pytest.raises(ValueError, match="No embedding data received"):
        parse_embeddings_response({
            "vectors": [],
            "base_resp": {"status_code": 0},
        })


def test_parse_accepts_openai_shaped_fallback():
    vectors, _ = parse_embeddings_response({
        "data": [
            {"index": 1, "embedding": [0.3]},
            {"index": 0, "embedding": [0.1]},
        ],
        "base_resp": {"status_code": 0},
    })
    assert vectors == [[0.1], [0.3]]


@pytest.mark.asyncio
async def test_router_embed_uses_minimax_native_api_not_openai_sdk(monkeypatch):
    from app.services import llm_router as llm_router_module

    router = llm_router_module.LLMRouter()
    monkeypatch.setattr(
        router,
        "get_provider_config_async",
        AsyncMock(return_value={
            "name": "MiniMax",
            "api_key": "sk-test",
            "base_url": "https://api.minimaxi.com/v1",
            "models": [{"name": "MiniMax-M3", "model_type": "chat"}],
            "metadata_json": {"group_id": "gid-1"},
            "provider_type": "openai",
        }),
    )
    openai_create = AsyncMock(side_effect=AssertionError("must not use OpenAI embeddings.create"))
    monkeypatch.setattr(
        router,
        "get_client_async",
        AsyncMock(return_value=SimpleNamespace(
            embeddings=SimpleNamespace(create=openai_create),
        )),
    )
    record = AsyncMock()
    monkeypatch.setattr(router, "_record_token_usage", record)

    posted = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "vectors": [[0.11, 0.22]],
                "total_tokens": 4,
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            posted["url"] = url
            posted["headers"] = headers
            posted["json"] = json
            return _Resp()

    with patch("app.services.minimax_embedder.httpx.AsyncClient", _Client):
        vectors = await router.embed(
            ["hello"],
            model="text-embedding-3-small",
            provider_id=7,
            embed_type="query",
        )

    assert vectors == [[0.11, 0.22]]
    assert posted["url"] == "https://api.minimaxi.com/v1/embeddings?GroupId=gid-1"
    assert posted["json"]["texts"] == ["hello"]
    assert posted["json"]["model"] == "embo-01"
    assert posted["json"]["type"] == "query"
    assert "input" not in posted["json"]
    openai_create.assert_not_called()
    record.assert_awaited()


@pytest.mark.asyncio
async def test_router_embed_openai_empty_data_has_actionable_error(monkeypatch):
    from app.services import llm_router as llm_router_module

    router = llm_router_module.LLMRouter()
    monkeypatch.setattr(router, "get_provider_config_async", AsyncMock(return_value={
        "name": "OpenAI",
        "api_key": "sk-test",
        "base_url": "https://api.openai.com/v1",
        "models": [],
        "metadata_json": {},
        "provider_type": "openai",
    }))
    response = SimpleNamespace(data=[], usage=None)
    monkeypatch.setattr(
        router,
        "get_client_async",
        AsyncMock(return_value=SimpleNamespace(
            embeddings=SimpleNamespace(create=AsyncMock(return_value=response)),
        )),
    )
    with pytest.raises(ValueError, match="No embedding data received"):
        await router.embed(["hello"], model="text-embedding-3-small", provider_id=1)
