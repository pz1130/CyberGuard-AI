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

def _over_budget(
    messages: List[Dict[str, Any]],
    compact_chars: int,
    *,
    max_tokens: Optional[int] = None,
) -> bool:
    """True when history should be compacted.

    Prefer weighted token budget (``max_tokens``). ``compact_chars=0`` means
    "caller already decided we are over budget — always compact if splittable".
    Legacy char path kept when only compact_chars is set.
    """
    if max_tokens is not None:
        from agent_core.tokens import estimate_tokens
        return estimate_tokens(messages) > max_tokens
    if compact_chars <= 0:
        return True
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
    max_tokens: Optional[int] = None,
    context_window: Optional[int] = None,
    reserve_output: int = 1024,
    reserve_system: int = 512,
) -> List[Dict[str, Any]]:
    """Summarise older messages when the buffer grows too large (INV-33/34).

    Prefer ``max_tokens`` or ``context_window`` (remaining-budget) over the
    legacy character threshold.
    """
    token_budget = max_tokens
    if token_budget is None and context_window is not None:
        from agent_core.tokens import remaining_budget
        token_budget = remaining_budget(
            context_window,
            reserve_output=reserve_output,
            reserve_system=reserve_system,
        )
    if not _over_budget(messages, compact_chars, max_tokens=token_budget):
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
