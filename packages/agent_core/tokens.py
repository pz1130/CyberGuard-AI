"""Token estimation with CJK-aware weighting (M0a-2).

Legacy ``chars // 4`` under-counts Chinese and blows past real context windows.
Heuristic (no external tokenizer dependency):
  * CJK ideographs / fullwidth → 1.0 token per char
  * everything else → ~0.25 token per char (4 chars ≈ 1 token)
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF  # CJK Unified
        or 0x3400 <= o <= 0x4DBF  # Extension A
        or 0xF900 <= o <= 0xFAFF  # Compatibility
        or 0x3000 <= o <= 0x303F  # CJK punctuation
        or 0xFF00 <= o <= 0xFFEF  # Fullwidth forms
    )


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if _is_cjk(ch):
            cjk += 1
        else:
            other += 1
    # ceil(other/4) without float
    return cjk + (other + 3) // 4


def estimate_tokens(messages: Iterable[Mapping[str, Any]]) -> int:
    """Sum weighted tokens across message contents (and tool_call args if present)."""
    total = 0
    for m in messages:
        content = m.get("content") if isinstance(m, Mapping) else None
        if not isinstance(content, str):
            content = str(content)
        total += estimate_text_tokens(content)
        for tc in (m.get("tool_calls") or []) if isinstance(m, Mapping) else []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += estimate_text_tokens(str(fn.get("name") or ""))
            total += estimate_text_tokens(str(fn.get("arguments") or ""))
    return total


def remaining_budget(
    context_window: int,
    *,
    reserve_output: int = 1024,
    reserve_system: int = 512,
) -> int:
    """Tokens available for history before compression should fire."""
    return max(256, int(context_window) - int(reserve_output) - int(reserve_system))
