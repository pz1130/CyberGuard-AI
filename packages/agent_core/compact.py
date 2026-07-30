"""In-run message compaction for the agent tool loop (from InternalAgentRunner).

Behavior-preserving M0a-1 extraction: system + digest + recent, or system +
recent on failure. Chat is injected so this package stays free of app/llm deps.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from agent_core.loop_utils import (
    AGENT_COMPACT_SYSTEM,
    CONTEXT_COMPACT_CHARS,
    CONTEXT_KEEP_RECENT,
    estimate_message_chars,
    messages_to_text,
    split_for_compact,
)

ChatFn = Callable[..., Awaitable[Any]]


async def maybe_compact_messages(
    messages: List[Dict[str, Any]],
    chat: ChatFn,
    *,
    compact_chars: int = CONTEXT_COMPACT_CHARS,
    keep_recent: int = CONTEXT_KEEP_RECENT,
    chat_kwargs: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Summarise older messages when the buffer grows too large.

    Keeps the leading system message and the last ``keep_recent`` messages
    verbatim; replaces the middle with an LLM-produced summary. On any failure
    falls back to simply dropping the middle.
    """
    if estimate_message_chars(messages) <= compact_chars:
        return messages

    parts = split_for_compact(messages, keep_recent=keep_recent)
    if parts is None:
        return messages
    system, middle, recent = parts

    summary_prompt = [
        {"role": "system", "content": AGENT_COMPACT_SYSTEM},
        {
            "role": "user",
            "content": "Summarize the conversation so far:\n\n" + messages_to_text(middle),
        },
    ]
    kwargs = dict(chat_kwargs or {})
    try:
        summary = await chat(messages=summary_prompt, **kwargs)
        if not isinstance(summary, str):
            summary = getattr(summary, "content", None) or ""
        summary = summary.strip()
        if not summary:
            raise ValueError("empty summary")
        digest = {
            "role": "system",
            "content": "## 对话摘要（早期消息已压缩）\n" + summary,
        }
        return [system, digest] + recent
    except Exception:
        return [system] + recent
