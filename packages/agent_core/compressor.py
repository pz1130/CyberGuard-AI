"""Context-history compression (M0a-2: six-segment summary + weighted tokens).

Pure functions are sync. Async orchestrators take an injected ``llm_router``-like
object with ``async chat(messages=...)``. Callers pass max_tokens / keep_last
(or context_window for remaining-budget thresholds).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from agent_core.tokens import estimate_tokens, remaining_budget

logger = logging.getLogger(__name__)

# Fixed six sections (INV-33). Constraints MUST carry live auth / targets / sandbox.
SUMMARY_PROMPT = (
    "你是会话历史压缩器。把以下对话压缩为**恰好六段**结构化要点（中文），"
    "每段用对应标题开头，不要省略任何一段：\n\n"
    "## Goal\n用户目标与已确认事实\n\n"
    "## Constraints\n当前生效的授权范围、目标白名单、沙箱模式、不可越界规则"
    "（若输入含 Constraints 块必须原样保留关键边界，不得弱化）\n\n"
    "## Progress\nDone / In Progress / Blocked\n\n"
    "## Key Decisions\n关键决策与依据\n\n"
    "## Next Steps\n下一步计划\n\n"
    "## Critical Context\n必须保留的引用、IOC、路径、命令、证据指针\n\n"
    "输出纯 markdown 六段标题+正文；不要额外前言。"
)

_SUMMARY_PROMPT = SUMMARY_PROMPT

SIX_SECTION_HEADERS = (
    "## Goal",
    "## Constraints",
    "## Progress",
    "## Key Decisions",
    "## Next Steps",
    "## Critical Context",
)


def format_constraints_block(constraints: Optional[Mapping[str, Any]]) -> str:
    """Render a constraints dict for injection into the compressor user message."""
    if not constraints:
        return (
            "[Constraints]\n"
            "authorization: (unspecified)\n"
            "target_whitelist: (unspecified)\n"
            "sandbox_mode: (unspecified)\n"
        )
    lines = ["[Constraints]"]
    for key in (
        "authorization",
        "auth_scope",
        "target_whitelist",
        "targets",
        "sandbox_mode",
        "sandbox",
    ):
        if key in constraints:
            lines.append(f"{key}: {constraints[key]}")
    for k, v in constraints.items():
        if k in (
            "authorization",
            "auth_scope",
            "target_whitelist",
            "targets",
            "sandbox_mode",
            "sandbox",
        ):
            continue
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def select_window(
    messages: Sequence[Mapping[str, str]],
    summary: str,
    keep_last: int,
    *,
    preserve_turn_from: Optional[int] = None,
) -> List[dict]:
    """Return `[summary_message] + tail`.

    ``preserve_turn_from`` (INV-34): current turn (from that index) is never
    dropped. Additional older messages fill up to ``keep_last`` total when
    the turn alone is shorter than ``keep_last``.
    """
    n = len(messages)
    if preserve_turn_from is not None and 0 <= preserve_turn_from < n:
        turn = list(messages[preserve_turn_from:])
        older = list(messages[:preserve_turn_from])
        need = max(0, keep_last - len(turn)) if keep_last > 0 else 0
        older_tail = older[-need:] if need > 0 else []
        tail: List[dict] = older_tail + turn
    else:
        tail = list(messages[-keep_last:]) if keep_last > 0 else []
    if summary:
        return [{"role": "system", "content": summary}, *tail]
    return tail


def find_current_turn_start(messages: Sequence[Mapping[str, Any]]) -> int:
    """Index of the last user message (start of current turn), or 0."""
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return 0


def build_summary_user_message(
    messages: Sequence[Mapping[str, str]],
    *,
    constraints: Optional[Mapping[str, Any]] = None,
) -> str:
    lines = [format_constraints_block(constraints), "", "[History]"]
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


_build_summary_user_message = build_summary_user_message


def ensure_constraints_in_summary(
    summary: str, constraints: Optional[Mapping[str, Any]]
) -> str:
    """If constraints were provided and the model dropped them, re-append."""
    text = (summary or "").strip()
    if not constraints:
        return text
    block = format_constraints_block(constraints)
    if "## Constraints" not in text:
        return f"## Constraints\n{block}\n\n{text}" if text else f"## Constraints\n{block}"
    lower = text.lower()
    if not any(
        str(v).lower() in lower
        for v in constraints.values()
        if v is not None and str(v)
    ):
        return text + "\n\n" + block
    return text


async def compress_history(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: int,
    keep_last: int,
    constraints: Optional[Mapping[str, Any]] = None,
    preserve_current_turn: bool = True,
) -> tuple[List[dict], Optional[str]]:
    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, None

    turn_from = find_current_turn_start(history_list) if preserve_current_turn else None

    if llm_router is None:
        logger.warning("context_compressor: llm_router is None; degrading to sliding window")
        return select_window(
            history_list, "", keep_last, preserve_turn_from=turn_from
        ), None

    try:
        response = await llm_router.chat(
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": build_summary_user_message(
                        history_list, constraints=constraints
                    ),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "context_compressor: LLM call failed; degrading to sliding window: %s", exc
        )
        return select_window(
            history_list, "", keep_last, preserve_turn_from=turn_from
        ), None

    summary = ensure_constraints_in_summary((response or "").strip(), constraints)
    if not summary:
        return select_window(
            history_list, "", keep_last, preserve_turn_from=turn_from
        ), None
    return (
        select_window(
            history_list, summary, keep_last, preserve_turn_from=turn_from
        ),
        summary,
    )


async def maybe_compress(
    history: Sequence[Mapping[str, str]],
    llm_router: Any,
    *,
    max_tokens: Optional[int] = None,
    keep_last: int = 6,
    context_window: Optional[int] = None,
    reserve_output: int = 1024,
    constraints: Optional[Mapping[str, Any]] = None,
    preserve_current_turn: bool = True,
) -> tuple[List[dict], bool, bool]:
    """Returns `(new_history, compressed, degraded)`.

    If ``context_window`` is set and ``max_tokens`` is not, threshold =
    remaining_budget(context_window, reserve_output=...).
    """
    if max_tokens is None:
        if context_window is not None:
            max_tokens = remaining_budget(
                context_window, reserve_output=reserve_output
            )
        else:
            max_tokens = 8000

    history_list = list(history)
    if estimate_tokens(history_list) < max_tokens:
        return history_list, False, False

    new, summary = await compress_history(
        history_list,
        llm_router,
        max_tokens=max_tokens,
        keep_last=keep_last,
        constraints=constraints,
        preserve_current_turn=preserve_current_turn,
    )
    if summary:
        return new, True, False
    return new, False, True
