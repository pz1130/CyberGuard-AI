"""HTTP adapter for MiniMax's native embeddings API."""
from __future__ import annotations

from types import SimpleNamespace
from typing import List, Optional, Sequence, Tuple

import httpx

from llm_router.minimax_embeddings import (
    DEFAULT_EMBED_MODEL,
    build_payload,
    embeddings_url,
    parse_embeddings_response,
    resolve_embed_model,
)

_BATCH_SIZE = 64
_TIMEOUT_S = 30.0


async def embed_texts(
    texts: Sequence[str],
    *,
    api_key: str,
    base_url: str,
    model: Optional[str] = None,
    group_id: Optional[str] = None,
    embed_type: str = "db",
) -> Tuple[List[List[float]], SimpleNamespace]:
    """POST MiniMax /embeddings. Returns (vectors, usage-like namespace)."""
    if not texts:
        return [], SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)

    resolved = resolve_embed_model(model)
    url = embeddings_url(base_url, group_id)
    from app.core.egress import enforce_egress
    url = enforce_egress(url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    all_vectors: List[List[float]] = []
    total_tokens = 0
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = list(texts[start : start + _BATCH_SIZE])
            payload = build_payload(batch, model=resolved or DEFAULT_EMBED_MODEL, embed_type=embed_type)
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                raise ValueError(f"MiniMax embeddings request failed: {e}") from e
            if resp.status_code >= 400:
                raise ValueError(
                    f"MiniMax embeddings HTTP {resp.status_code}: {resp.text[:300]}"
                )
            try:
                body = resp.json()
            except Exception as e:  # noqa: BLE001
                raise ValueError("MiniMax embeddings did not return JSON") from e
            vectors, tokens = parse_embeddings_response(body)
            if len(vectors) != len(batch):
                raise ValueError(
                    f"MiniMax embedding count mismatch: expected {len(batch)}, got {len(vectors)}"
                )
            all_vectors.extend(vectors)
            total_tokens += tokens

    usage = SimpleNamespace(
        prompt_tokens=total_tokens,
        completion_tokens=0,
        total_tokens=total_tokens,
    )
    return all_vectors, usage
