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
    select_window,
)
from agent_core.compressor import maybe_compress as _maybe_compress_core
from agent_core.tokens import estimate_tokens, remaining_budget  # noqa: F401


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
    context_window: Optional[int] = None,
    reserve_output: Optional[int] = None,
    reserve_system: Optional[int] = None,
    constraints: Optional[Mapping[str, Any]] = None,
    preserve_current_turn: bool = True,
) -> tuple[List[dict], bool, bool]:
    """Hook used by callers. Returns `(new_history, compressed, degraded)`.

    Preferred (M0a-2): pass ``context_window`` (+ optional reserves) so the
    threshold is ``remaining_budget(context_window)``. Absolute ``max_tokens``
    remains supported as an override / fallback from settings.
    """
    from app.config import settings

    cfg_max, cfg_keep = _read_settings()
    if keep_last is None:
        keep_last = cfg_keep

    if reserve_output is None:
        reserve_output = int(
            getattr(settings, "CONTEXT_COMPRESS_RESERVE_OUTPUT", 1024)
        )
    if reserve_system is None:
        reserve_system = int(
            getattr(settings, "CONTEXT_COMPRESS_RESERVE_SYSTEM", 512)
        )

    # Prefer remaining-budget path when context_window is known and max_tokens
    # was not explicitly forced by the caller.
    if context_window is not None and max_tokens is None:
        return await _maybe_compress_core(
            history,
            llm_router,
            max_tokens=None,
            keep_last=keep_last,
            context_window=context_window,
            reserve_output=reserve_output,
            reserve_system=reserve_system,
            constraints=constraints,
            preserve_current_turn=preserve_current_turn,
        )

    if max_tokens is None:
        max_tokens = cfg_max

    return await _maybe_compress_core(
        history,
        llm_router,
        max_tokens=max_tokens,
        keep_last=keep_last,
        constraints=constraints,
        preserve_current_turn=preserve_current_turn,
    )


__all__ = [
    "estimate_tokens",
    "remaining_budget",
    "select_window",
    "build_summary_user_message",
    "compress_history",
    "maybe_compress",
    "SUMMARY_PROMPT",
]
