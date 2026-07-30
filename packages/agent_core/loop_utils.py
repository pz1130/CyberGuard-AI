"""Pure helpers for the agent tool-call loop (M0a-1).

No I/O. Used by ``run_loop`` and re-exported through InternalAgentRunner for
backward-compatible unit tests.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# Defaults aligned with existing InternalAgentRunner tunables.
TOOL_RESULT_MAX_CHARS = 8000
AUTO_CONTINUE_MAX = 2
CONTEXT_COMPACT_CHARS = 24000
CONTEXT_KEEP_RECENT = 6
LOOP_DETECT_THRESHOLD = 3
REFLECT_MAX = 2
LLM_RETRY_MAX = 2
LLM_RETRY_BACKOFF = 0.5
TOOL_CALL_BUDGET_DEFAULT = 100
TOOL_CALL_BUDGET_LIMITED = 20

REFLECT_GUIDANCE = (
    "你似乎在重复同一个操作且没有进展。请停下来反思：要么换一种"
    "完全不同的方法或参数，要么基于已有信息直接给出最终答复。"
)

AGENT_COMPACT_SYSTEM = (
    "You compress conversation history for an AI agent. Produce a concise "
    "summary that preserves facts, user intent, decisions, and key tool "
    "results. Use markdown with ## section headers."
)


def tool_call_fingerprint(name: str, arguments: str) -> str:
    """Stable identity for a tool call: name + order-invariant arguments."""
    try:
        norm = json.dumps(
            json.loads(arguments or "{}"), sort_keys=True, ensure_ascii=False
        )
    except (json.JSONDecodeError, TypeError):
        norm = arguments or ""
    return f"{name}::{norm}"


def loop_notice(name: str, count: int) -> str:
    return (
        f"LOOP_DETECTED: 你已用相同参数调用 {name} {count} 次，结果不会改变。"
        f"请改用其他工具或参数，或直接给出最终答复。"
    )


def budget_notice(budget: int) -> str:
    return (
        f"BUDGET_EXHAUSTED: 已达到工具调用上限（{budget} 次），"
        f"该调用未执行。请基于已有信息给出最终答复。"
    )


def truncate_tool_result(
    text: Optional[str], *, max_chars: int = TOOL_RESULT_MAX_CHARS
) -> str:
    """Cap a single tool result so noisy tools can't blow the context."""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    dropped = len(text) - max_chars
    return text[:max_chars] + f"\n…[truncated {dropped} chars]"


def estimate_message_chars(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        total += len(str(m.get("content") or ""))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += len(str(fn.get("arguments") or "")) + len(str(fn.get("name") or ""))
    return total


def messages_to_text(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = str(m.get("content") or "")
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            content += f" [tool_call {fn.get('name')}({fn.get('arguments')})]"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def split_for_compact(
    messages: List[Dict[str, Any]],
    *,
    keep_recent: int = CONTEXT_KEEP_RECENT,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]] | None:
    """Split into (system, middle, recent) or None if too short to compact.

    INV-34: recent always includes the current turn (from last user message)
    *and* at least ``keep_recent`` messages when possible.
    Drops orphaned leading ``tool`` messages from the recent window.
    """
    if len(messages) <= keep_recent + 2:
        return None
    system = messages[0]
    turn_start = 1
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "user":
            turn_start = i
            break
    tail_start = max(1, len(messages) - keep_recent)
    # Earlier index keeps more history in "recent" so the full current turn survives.
    recent_start = min(turn_start, tail_start)
    recent = list(messages[recent_start:])
    while recent and recent[0].get("role") == "tool":
        recent = recent[1:]
    middle = messages[1 : len(messages) - len(recent)]
    if not middle:
        return None
    return system, middle, recent
