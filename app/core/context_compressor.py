"""Per-turn context-history compression for the master agent.

M0a-1: pure + async implementation lives in ``agent_core.compressor``.
This module re-exports the public API and keeps ``maybe_compress`` able to
read app settings when max_tokens / keep_last are omitted.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence

from agent_core.compressor import (  # noqa: F401
    SUMMARY_PROMPT,
    _SUMMARY_PROMPT,
    _build_summary_user_message,
    build_summary_user_message,
    compress_history,
    estimate_tokens,
    select_window,
)
from agent_core.compressor import maybe_compress as _maybe_compress_core


def _read_settings() -> tuple[int, int]:
    """Lazy import to avoid circular import / test discovery ordering issues."""
    from app.config import settings  # noqa: WPS433

    return (
        int(getattr(settings, "CONTEXT_COMPRESS_MAX_TOKENS", 8000)),
        int(getattr(settings, "CONTEXT_COMPRESS_KEEP_LAST", 6)),
    )


async def maybe_compress(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: Optional[int] = None,
    keep_last: Optional[int] = None,
) -> tuple[List[dict], bool, bool]:
    """Hook used by callers. Returns `(new_history, compressed, degraded)`.

    Resolves defaults from app settings when not provided (server wiring).
    """
    if max_tokens is None or keep_last is None:
        cfg_max, cfg_keep = _read_settings()
        max_tokens = cfg_max if max_tokens is None else max_tokens
        keep_last = cfg_keep if keep_last is None else keep_last

    return await _maybe_compress_core(
        history, llm_router, max_tokens=max_tokens, keep_last=keep_last
    )


__all__ = [
    "estimate_tokens",
    "select_window",
    "build_summary_user_message",
    "compress_history",
    "maybe_compress",
    "SUMMARY_PROMPT",
]
