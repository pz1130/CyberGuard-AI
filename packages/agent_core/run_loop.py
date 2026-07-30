"""Agent tool-call run loop — deployment-agnostic core (M0a-1).

Moved from ``InternalAgentRunner._run_loop`` with I/O behind ports:
  * ``chat`` — LLM completion (may return str or message with tool_calls)
  * ``dispatch`` — execute one tool_call, return string result
  * ``compact`` — optional in-run history compaction

No app.*, DB, or FastAPI imports.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Sequence

from agent_core.loop_utils import (
    AUTO_CONTINUE_MAX,
    LLM_RETRY_BACKOFF,
    LLM_RETRY_MAX,
    LOOP_DETECT_THRESHOLD,
    REFLECT_GUIDANCE,
    REFLECT_MAX,
    TOOL_RESULT_MAX_CHARS,
    budget_notice,
    loop_notice,
    tool_call_fingerprint,
    truncate_tool_result,
)

logger = logging.getLogger(__name__)

ChatPort = Callable[..., Awaitable[Any]]
DispatchPort = Callable[[Any], Awaitable[str]]
CompactPort = Callable[[List[Dict[str, Any]]], Awaitable[List[Dict[str, Any]]]]


@dataclass
class RunLoopConfig:
    max_steps: int
    tool_call_budget: int
    agent_id: Any = None
    agent_name: str = ""
    auto_continue_max: int = AUTO_CONTINUE_MAX
    loop_detect_threshold: int = LOOP_DETECT_THRESHOLD
    reflect_max: int = REFLECT_MAX
    llm_retry_max: int = LLM_RETRY_MAX
    llm_retry_backoff: float = LLM_RETRY_BACKOFF
    tool_result_max_chars: int = TOOL_RESULT_MAX_CHARS
    reflect_guidance: str = REFLECT_GUIDANCE


async def run_loop(
    *,
    task: str,
    system_prompt: str,
    history: Sequence[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    config: RunLoopConfig,
    chat: ChatPort,
    dispatch: DispatchPort,
    compact: Optional[CompactPort] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Shared tool-call loop. Yields semantic events (same shape as before).

      {"type": "start", "agent_id", "agent_name"}
      {"type": "tool_call_start", "name", "arguments", "call_id"}
      {"type": "tool_call_end", "name", "call_id", "result_preview", "error"}
      {"type": "answer_ready", "messages", "new_messages",
                               "candidate_text", "tool_call_log"}
      {"type": "error", "status": "failed"|"error", "error", ["tool_call_log"]}
      {"type": "reflection", ...}
    """
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(list(history))
    messages.append({"role": "user", "content": task})

    new_messages: List[Dict[str, Any]] = [{"role": "user", "content": task}]
    tool_call_log: List[Dict[str, Any]] = []

    tool_used_ever = False
    auto_continue_used = 0
    fingerprints: Counter = Counter()
    reflections_used = 0
    tool_calls_made = 0
    active_tools = tools

    yield {
        "type": "start",
        "agent_id": config.agent_id,
        "agent_name": config.agent_name,
    }

    for step in range(config.max_steps):
        if compact is not None:
            messages = await compact(messages)

        msg = None
        last_err: Optional[Exception] = None
        for attempt in range(config.llm_retry_max + 1):
            try:
                msg = await chat(
                    messages=messages,
                    tools=active_tools if active_tools else None,
                )
                break
            except Exception as e:
                last_err = e
                if attempt < config.llm_retry_max:
                    yield {
                        "type": "reflection",
                        "reason": "llm_error",
                        "attempt": attempt + 1,
                    }
                    await asyncio.sleep(config.llm_retry_backoff * (attempt + 1))
        if msg is None:
            yield {
                "type": "error",
                "status": "failed",
                "error": (
                    f"LLM error at step {step} after "
                    f"{config.llm_retry_max + 1} attempts: {last_err}"
                ),
            }
            return

        if isinstance(msg, str):
            tool_calls = None
            text_only = True
            candidate_text = msg
        else:
            tool_calls = getattr(msg, "tool_calls", None)
            text_only = not tool_calls
            candidate_text = getattr(msg, "content", None) or ""

        if text_only:
            if (
                active_tools
                and not tool_used_ever
                and auto_continue_used < config.auto_continue_max
            ):
                auto_continue_used += 1
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "如果任务尚未完成，请调用相应工具继续；"
                            "如果确认已完成，请直接给出最终答复。"
                        ),
                    }
                )
                continue
            yield {
                "type": "answer_ready",
                "messages": messages,
                "new_messages": new_messages,
                "candidate_text": candidate_text,
                "tool_call_log": tool_call_log,
            }
            return

        tool_used_ever = True
        assistant_msg = {
            "role": "assistant",
            "content": getattr(msg, "content", None) or "",
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.function.name,
                        "arguments": c.function.arguments,
                    },
                }
                for c in tool_calls
            ],
        }
        messages.append(assistant_msg)
        new_messages.append(assistant_msg)

        for c in tool_calls:
            yield {
                "type": "tool_call_start",
                "name": c.function.name,
                "arguments": c.function.arguments,
                "call_id": c.id,
            }

        loop_hit = False
        budget_hit = False

        async def _dispatch_or_reflect(call):
            nonlocal loop_hit, budget_hit, tool_calls_made
            if tool_calls_made >= config.tool_call_budget:
                budget_hit = True
                logger.warning(
                    "agent %s: tool-call budget (%d) exhausted",
                    config.agent_name,
                    config.tool_call_budget,
                )
                return budget_notice(config.tool_call_budget)
            tool_calls_made += 1
            fp = tool_call_fingerprint(call.function.name, call.function.arguments)
            fingerprints[fp] += 1
            if fingerprints[fp] >= config.loop_detect_threshold:
                loop_hit = True
                logger.warning(
                    "agent %s: tool-call loop on %r (x%d)",
                    config.agent_name,
                    call.function.name,
                    fingerprints[fp],
                )
                return loop_notice(call.function.name, fingerprints[fp])
            return await dispatch(call)

        results = await asyncio.gather(
            *[_dispatch_or_reflect(c) for c in tool_calls]
        )
        for call, result_str in zip(tool_calls, results):
            result_str = truncate_tool_result(
                result_str, max_chars=config.tool_result_max_chars
            )
            tool_call_log.append(
                {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                    "result_preview": result_str[:200],
                }
            )
            tool_msg = {
                "role": "tool",
                "tool_call_id": call.id,
                "content": result_str,
            }
            messages.append(tool_msg)
            new_messages.append(tool_msg)
            yield {
                "type": "tool_call_end",
                "name": call.function.name,
                "call_id": call.id,
                "result_preview": result_str[:200],
                "error": result_str.startswith(
                    ("ERROR", "LOOP_DETECTED", "BUDGET_EXHAUSTED")
                ),
            }

        if budget_hit:
            active_tools = None
            yield {
                "type": "reflection",
                "reason": "budget",
                "tool_calls_made": tool_calls_made,
            }
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"已达到本次任务的工具调用上限（{config.tool_call_budget} 次），"
                        f"不会再执行任何工具。请基于已获取的信息直接给出最终答复。"
                    ),
                }
            )
            continue

        if loop_hit:
            reflections_used += 1
            yield {
                "type": "reflection",
                "reason": "loop",
                "count": reflections_used,
            }
            if reflections_used > config.reflect_max:
                yield {
                    "type": "error",
                    "status": "error",
                    "error": (
                        f"aborted: agent stuck in a tool-call loop "
                        f"(repeated identical calls); reflector gave up "
                        f"after {config.reflect_max} nudges"
                    ),
                    "tool_call_log": tool_call_log,
                }
                return
            messages.append({"role": "user", "content": config.reflect_guidance})

    yield {
        "type": "error",
        "status": "error",
        "error": f"exceeded tool_loop_max_steps ({config.max_steps})",
        "tool_call_log": tool_call_log,
    }
