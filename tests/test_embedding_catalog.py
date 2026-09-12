"""Embedding-model catalog helpers: MiniMax embo-01 backfill + save validation."""
import pytest

from app.services.embedding_catalog import (
    classify_model_type,
    ensure_provider_embedding_models,
    looks_like_embedding_model,
    validate_embedding_models,
)


def test_classify_minimax_and_openai_embedding_names():
    assert classify_model_type("embo-01") == "embedding"
    assert classify_model_type("text-embedding-3-small") == "embedding"
    assert classify_model_type("BAAI/bge-m3") == "embedding"
    assert classify_model_type("bge-reranker-v2-m3") == "rerank"
    assert looks_like_embedding_model("bge-reranker-v2-m3") is False
    assert classify_model_type("MiniMax-M3") == "chat"
    assert classify_model_type("gpt-4o") == "chat"


def test_ensure_adds_embo_01_on_minimax_without_dropping_chat_models():
    models = [
        {"name": "MiniMax-M3", "model_type": "chat"},
        {"name": "MiniMax-M2.5", "model_type": "chat"},
    ]
    out = ensure_provider_embedding_models(
        models, base_url="https://api.minimaxi.com/v1", name="MiniMax",
    )
    names = [m["name"] for m in out]
    assert "MiniMax-M3" in names
    assert "embo-01" in names
    embo = next(m for m in out if m["name"] == "embo-01")
    assert embo["model_type"] == "embedding"
    # Idempotent
    again = ensure_provider_embedding_models(
        out, base_url="https://api.minimaxi.com/v1", name="MiniMax",
    )
    assert [m["name"] for m in again].count("embo-01") == 1


def test_ensure_does_not_inject_embo_on_openai():
    models = [{"name": "gpt-4o", "model_type": "chat"}]
    out = ensure_provider_embedding_models(
        models, base_url="https://api.openai.com/v1", name="OpenAI",
    )
    assert [m["name"] for m in out] == ["gpt-4o"]


def test_validate_rejects_minimax_chat_model_marked_as_embedding():
    with pytest.raises(ValueError, match="embo-01"):
        validate_embedding_models(
            [{"name": "MiniMax-M3", "model_type": "embedding"}],
            base_url="https://api.minimaxi.com/v1",
            name="MiniMax",
        )


def test_validate_accepts_embo_01():
    validate_embedding_models(
        [
            {"name": "MiniMax-M3", "model_type": "chat"},
            {"name": "embo-01", "model_type": "embedding"},
        ],
        base_url="https://api.minimaxi.com/v1",
        name="MiniMax",
    )
