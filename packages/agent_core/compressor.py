"""Context-history compression primitives (M0a-1 move from app.core.context_compressor).

Pure functions are sync and side-effect free. Async orchestrators take an
injected ``llm_router``-like object with ``async chat(messages=...)`` and never
import app config — callers pass max_tokens / keep_last.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# Module-level summary prompt (Chinese, matching existing master-agent style).
SUMMARY_PROMPT = (
    "你是会话历史压缩器。请把以下对话压缩为结构化要点(中文, ≤ 600 字):\n\n"
    "1. 用户目标与已确认事实\n"
    "2. 待办 / 未决问题\n"
    "3. 关键引用(原文短语)\n"
    "4. 不确定 / 已废弃的想法\n\n"
    "输出纯文本,不要使用 markdown / 列表前缀 / 标题。"
)

# Back-compat alias for any code that imported the private name.
_SUMMARY_PROMPT = SUMMARY_PROMPT


def estimate_tokens(messages: Iterable[Mapping[str, Any]]) -> int:
    """Rough token estimate: sum of content character lengths divided by 4.

    Conservative for CJK content (counts chars, not bytes). Tolerates missing
    or non-string `content` by coercing via `str()`.
    """
    total_chars = 0
    for m in messages:
        content = m.get("content") if isinstance(m, Mapping) else None
        if not isinstance(content, str):
            content = str(content)
        total_chars += len(content)
    return total_chars // 4


def select_window(
    messages: Sequence[Mapping[str, str]],
    summary: str,
    keep_last: int,
) -> List[dict]:
    """Return `[summary_message] + tail` if `summary` is non-empty; else `tail`.

    `keep_last <= 0` collapses the tail; with an empty summary the result is
    an empty list. The summary is always returned as a `system`-role message.
    """
    tail: List[dict] = list(messages[-keep_last:]) if keep_last > 0 else []
    if summary:
        return [{"role": "system", "content": summary}, *tail]
    return tail


def build_summary_user_message(messages: Sequence[Mapping[str, str]]) -> str:
    """Format the history as a single user-role message, role-prefixed lines."""
    lines = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


# Private name used by older call sites / tests that introspect.
_build_summary_user_message = build_summary_user_message


async def compress_history(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: int,
    keep_last: int,
) -> tuple[List[dict], Optional[str]]:
    """Core async orchestrator.

    Returns `(new_history, summary_str_or_None)`.
    - If `estimate_tokens(history) < max_tokens` → returns `(list(history), None)`
      without calling the LLM.
    - Otherwise calls `llm_router.chat(...)` once. On success returns the window
      with the summary prepended. On any exception, logs and returns the
      keep_last tail with `summary=None`.
    """
    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, None

    if llm_router is None:
        logger.warning("context_compressor: llm_router is None; degrading to sliding window")
        return select_window(history_list, "", keep_last), None

    try:
        response = await llm_router.chat(
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": build_summary_user_message(history_list)},
            ]
        )
    except Exception as exc:  # noqa: BLE001 - intentional broad catch
        logger.warning(
            "context_compressor: LLM call failed; degrading to sliding window: %s", exc
        )
        return select_window(history_list, "", keep_last), None

    summary = (response or "").strip()
    return select_window(history_list, summary, keep_last), (summary or None)


async def maybe_compress(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: int,
    keep_last: int,
) -> tuple[List[dict], bool, bool]:
    """Returns `(new_history, compressed, degraded)`.

    Callers that previously read app settings must resolve max_tokens / keep_last
    before calling (app.core.context_compressor.maybe_compress does that).
    """
    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, False, False

    new, summary = await compress_history(
        history_list, llm_router, max_tokens=max_tokens, keep_last=keep_last
    )
    if summary:
        return new, True, False
    return new, False, True
