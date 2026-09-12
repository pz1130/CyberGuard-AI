"""Helpers for classifying embedding models and backfilling MiniMax embo-01."""
from __future__ import annotations

from typing import Any, Iterable, List, Optional

from llm_router.minimax_embeddings import DEFAULT_EMBED_MODEL, is_minimax_base_url

_EMBED_NEEDLES = (
    "embed",
    "embo",
    "bge-",
    "/bge",
    "e5-",
    "gte-",
    "nomic-embed",
    "text-embedding",
)


def looks_like_embedding_model(name: Optional[str]) -> bool:
    if looks_like_rerank_model(name):
        return False
    n = (name or "").lower()
    return any(needle in n for needle in _EMBED_NEEDLES)


def looks_like_rerank_model(name: Optional[str]) -> bool:
    return "rerank" in (name or "").lower()


def classify_model_type(name: Optional[str], current: Optional[str] = None) -> str:
    if looks_like_rerank_model(name):
        return "rerank"
    if looks_like_embedding_model(name):
        return "embedding"
    return current or "chat"


def is_minimax_provider(
    base_url: Optional[str] = None,
    name: Optional[str] = None,
    provider_type: Optional[str] = None,
) -> bool:
    if is_minimax_base_url(base_url):
        return True
    if (provider_type or "").lower() == "minimax":
        return True
    return "minimax" in (name or "").lower()


def _as_model_dicts(models: Optional[Iterable[Any]]) -> List[dict]:
    out: List[dict] = []
    for m in models or []:
        if isinstance(m, dict):
            out.append(dict(m))
        elif hasattr(m, "model_dump"):
            out.append(m.model_dump())
        else:
            out.append({"name": str(m), "model_type": "chat"})
    return out


def ensure_provider_embedding_models(
    models: Optional[Iterable[Any]],
    *,
    base_url: Optional[str] = None,
    name: Optional[str] = None,
    provider_type: Optional[str] = None,
) -> List[dict]:
    """For MiniMax, guarantee an `embo-01` embedding model entry exists."""
    result = _as_model_dicts(models)
    if not is_minimax_provider(base_url, name, provider_type):
        return result
    if any(
        (m.get("name") == DEFAULT_EMBED_MODEL and m.get("model_type") == "embedding")
        for m in result
    ):
        return result
    existing = next((m for m in result if m.get("name") == DEFAULT_EMBED_MODEL), None)
    if existing is not None:
        existing["model_type"] = "embedding"
        return result
    result.append({"name": DEFAULT_EMBED_MODEL, "model_type": "embedding"})
    return result


def validate_embedding_models(
    models: Optional[Iterable[Any]],
    *,
    base_url: Optional[str] = None,
    name: Optional[str] = None,
    provider_type: Optional[str] = None,
) -> None:
    """Reject MiniMax chat models marked as embedding.

    MiniMax embeddings only work via the native embo-01 API, not by tagging a
    chat model as `model_type=embedding`.
    """
    if not is_minimax_provider(base_url, name, provider_type):
        return
    for m in _as_model_dicts(models):
        if m.get("model_type") != "embedding":
            continue
        model_name = m.get("name") or ""
        if looks_like_embedding_model(model_name):
            continue
        raise ValueError(
            f"{model_name} is a MiniMax chat model and cannot produce embeddings. "
            f"Add {DEFAULT_EMBED_MODEL} with type 'embedding' (native MiniMax embeddings API)."
        )
