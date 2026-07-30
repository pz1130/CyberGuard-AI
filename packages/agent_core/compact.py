"""In-run message compaction for the agent tool loop (M0a-2 six-segment)."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from agent_core.compressor import (
    SUMMARY_PROMPT,
    ensure_constraints_in_summary,
    format_constraints_block,
)
from agent_core.loop_utils import (
    CONTEXT_COMPACT_CHARS,
    CONTEXT_KEEP_RECENT,
    estimate_message_chars,
    messages_to_text,
    split_for_compact,
)
from agent_core.tokens import estimate_text_tokens

ChatFn = Callable[..., Awaitable[Any]]

# Prefer weighted tokens for threshold when messages are long CJK.
def _over_budget(messages: List[Dict[str, Any]], compact_chars: int) -> bool:
    # compact_chars is historical char budget (~4 chars/token * tokens)
    # Convert to token budget roughly: compact_chars // 4 as floor, but also
    # fire if weighted tokens exceed compact_chars // 2 for CJK-heavy buffers.
    if estimate_message_chars(messages) > compact_chars:
        return True
    text = messages_to_text(messages)
    return estimate_text_tokens(text) > max(256, compact_chars // 2)


async def maybe_compact_messages(
    messages: List[Dict[str, Any]],
    chat: ChatFn,
    *,
    compact_chars: int = CONTEXT_COMPACT_CHARS,
    keep_recent: int = CONTEXT_KEEP_RECENT,
    chat_kwargs: Optional[Dict[str, Any]] = None,
    constraints: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Summarise older messages when the buffer grows too large (INV-33/34).

    Current turn (from last user message) stays in ``recent`` via split_for_compact
    + keep_recent, and orphan tool messages are dropped from the recent window.
    """
    if not _over_budget(messages, compact_chars):
        return messages

    parts = split_for_compact(messages, keep_recent=keep_recent)
    if parts is None:
        return messages
    system, middle, recent = parts

    user_body = (
        format_constraints_block(constraints)
        + "\n\nSummarize the conversation so far into the six required sections:\n\n"
        + messages_to_text(middle)
    )
    summary_prompt = [
        {"role": "system", "content": SUMMARY_PROMPT},
        {"role": "user", "content": user_body},
    ]
    kwargs = dict(chat_kwargs or {})
    try:
        summary = await chat(messages=summary_prompt, **kwargs)
        if not isinstance(summary, str):
            summary = getattr(summary, "content", None) or ""
        summary = ensure_constraints_in_summary(summary.strip(), constraints)
        if not summary:
            raise ValueError("empty summary")
        digest = {
            "role": "system",
            "content": "## 对话摘要（早期消息已压缩）\n" + summary,
        }
        return [system, digest] + recent
    except Exception:
        return [system] + recent
