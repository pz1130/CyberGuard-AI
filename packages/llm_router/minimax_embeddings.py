"""MiniMax native embeddings protocol (not OpenAI /embeddings compatible).

Chat on MiniMax is OpenAI-compatible (`/v1/chat/completions`). The embedding
API is a separate shape:

  POST {base}/embeddings[?GroupId=...]
  body:  {"model": "embo-01", "texts": [...], "type": "db"|"query"}
  reply: {"vectors": [[...], ...], "total_tokens": N,
          "base_resp": {"status_code": 0, "status_msg": "success"}}

Calling the OpenAI SDK (`embeddings.create` with `input=`) against MiniMax
returns HTTP 400 "No embedding data received".
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_EMBED_MODEL = "embo-01"
DEFAULT_EMBED_DIM = 1536
MINIMAX_HOST_MARKERS = (
    "minimax.io",
    "minimaxi.com",
    "minimax.chat",
    "minimax.cn",
    "minimax.com",
)
_VALID_EMBED_TYPES = {"db", "query"}


def is_minimax_base_url(base_url: Optional[str]) -> bool:
    host = (base_url or "").lower()
    return any(marker in host for marker in MINIMAX_HOST_MARKERS)


def resolve_embed_model(model: Optional[str]) -> str:
    """Map OpenAI-style embedding names (KB defaults) onto MiniMax embo-01."""
    name = (model or "").strip()
    if not name:
        return DEFAULT_EMBED_MODEL
    lowered = name.lower()
    if lowered.startswith("text-embedding") or lowered in {
        "text-embedding-3-small",
        "text-embedding-3-large",
        "text-embedding-ada-002",
    }:
        return DEFAULT_EMBED_MODEL
    return name


def embeddings_url(base_url: str, group_id: Optional[str] = None) -> str:
    url = (base_url or "").rstrip("/") + "/embeddings"
    gid = (group_id or "").strip()
    if not gid:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["GroupId"] = gid
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_payload(
    texts: Sequence[str],
    model: str = DEFAULT_EMBED_MODEL,
    embed_type: str = "db",
) -> dict:
    kind = embed_type if embed_type in _VALID_EMBED_TYPES else "db"
    return {
        "model": model or DEFAULT_EMBED_MODEL,
        "texts": list(texts),
        "type": kind,
    }


def parse_embeddings_response(payload: Any) -> Tuple[List[List[float]], int]:
    """Return (vectors, total_tokens). Raises ValueError on MiniMax/empty errors."""
    if not isinstance(payload, dict):
        raise ValueError("No embedding data received from MiniMax.")

    base_resp = payload.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code not in (0, None):
        msg = base_resp.get("status_msg") or f"status_code={status_code}"
        raise ValueError(f"MiniMax embeddings failed: {msg}")

    vectors = payload.get("vectors")
    if not vectors:
        data = payload.get("data")
        if isinstance(data, list) and data:
            ordered = sorted(
                (d for d in data if isinstance(d, dict)),
                key=lambda d: d.get("index", 0),
            )
            vectors = [d.get("embedding") for d in ordered]

    if not vectors or not isinstance(vectors, Iterable):
        raise ValueError(
            "No embedding data received from MiniMax. "
            "Use model embo-01 (not a chat model) and, for the CN endpoint, set GroupId."
        )

    out: List[List[float]] = []
    for vec in vectors:
        if not isinstance(vec, (list, tuple)) or not vec:
            raise ValueError("No embedding data received from MiniMax.")
        out.append([float(x) for x in vec])
    tokens = payload.get("total_tokens") or 0
    try:
        tokens = int(tokens)
    except (TypeError, ValueError):
        tokens = 0
    return out, tokens
