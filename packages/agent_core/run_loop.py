"""Agent tool-call run loop — deployment-agnostic core (M0a-1).

Moved from ``InternalAgentRunner._run_loop`` with I/O behind ports:
  * ``chat`` — LLM completion (may return str or message with tool_calls)
  * ``dispatch`` — execute one tool_call, return string result
  * ``compact`` — optional in-run history compaction
  * ``audit_bus`` — optional AuditBus (default process bus; empty = no-op)

No app.*, DB, or FastAPI imports.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Sequence, TYPE_CHECKING

from agent_core.events import AuditLayer, AuditPhase, emit_audit
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
from agent_core.messages import messages_for_model
from agent_core.tool_result import normalize_tool_result

if TYPE_CHECKING:
    from agent_core.events import AuditBus

logger = logging.getLogger(__name__)

ChatPort = Callable[..., Awaitable[Any]]
DispatchPort = Callable[[Any], Awaitable[str]]
CompactPort = Callable[[List[Dict[str, Any]]], Awaitable[List[Dict[str, Any]]]]
# Returns "sequential" | "parallel" for a tool_call object
ExecutionModePort = Callable[[Any], str]


def _should_run_parallel(
    tool_calls: Sequence[Any],
    *,
    default_mode: str,
    execution_mode_for: Optional[ExecutionModePort],
) -> bool:
    """INV-31 one-vote veto: parallel only if default is parallel OR every tool is parallel.

    Default is sequential. A single sequential (or unknown) tool forces sequential.
    """
    if not tool_calls:
        return False
    modes = []
    for c in tool_calls:
        if execution_mode_for is not None:
            modes.append((execution_mode_for(c) or "sequential").lower())
        else:
            modes.append((default_mode or "sequential").lower())
    if any(m != "parallel" for m in modes):
        return False
    return True


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
    tool_result_max_lines: Optional[int] = None
    # "tail" keep head (default); "head" keep tail — for log-like tools
    tool_truncate_mode: str = "tail"
    reflect_guidance: str = REFLECT_GUIDANCE
    agent_run_id: Optional[str] = None
    # INV-31: default sequential; parallel only if every tool opts in
    default_execution_mode: str = "sequential"


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
    audit_bus: Optional["AuditBus"] = None,
    execution_mode_for: Optional[ExecutionModePort] = None,
    abort_event: Optional[asyncio.Event] = None,
    steer_queue: Optional[asyncio.Queue] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Shared tool-call loop. Yields semantic events (same shape as before).

    Audit events (INV-29) are emitted via ``audit_bus`` / process default and
    are always awaited. With zero subscribers this is a no-op.

    M1 controls:
      * ``abort_event`` — if set, stop at the next step boundary (status=aborted)
      * ``steer_queue`` — drained each step; each item is a user message string
        appended to the context (skip current model step semantics: inject then
        continue so the next chat sees the steer)
    """
    agent_run_id = config.agent_run_id or str(uuid.uuid4())
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

    await emit_audit(
        audit_bus,
        layer=AuditLayer.AGENT,
        phase=AuditPhase.START,
        name=config.agent_name or "agent",
        payload={"task_preview": (task or "")[:200]},
        agent_run_id=agent_run_id,
    )

    yield {
        "type": "start",
        "agent_id": config.agent_id,
        "agent_name": config.agent_name,
        "agent_run_id": agent_run_id,
    }

    terminal_status = "error"
    terminal_error: Optional[str] = None

    try:
        for step in range(config.max_steps):
            if abort_event is not None and abort_event.is_set():
                terminal_status = "aborted"
                terminal_error = "aborted by user"
                yield {
                    "type": "error",
                    "status": "aborted",
                    "error": terminal_error,
                    "tool_call_log": tool_call_log,
                }
                return

            # Steer: inject user messages before the model step (M1)
            if steer_queue is not None:
                while True:
                    try:
                        steered = steer_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if steered is None:
                        continue
                    text = str(steered)
                    messages.append({"role": "user", "content": text})
                    new_messages.append({"role": "user", "content": text})
                    yield {"type": "steer", "message": text}

            turn_id = f"{agent_run_id}:{step}"
            await emit_audit(
                audit_bus,
                layer=AuditLayer.TURN,
                phase=AuditPhase.START,
                name=f"step_{step}",
                payload={"step": step},
                agent_run_id=agent_run_id,
                turn_id=turn_id,
            )

            if compact is not None:
                messages = await compact(messages)

            msg = None
            last_err: Optional[Exception] = None
            for attempt in range(config.llm_retry_max + 1):
                if abort_event is not None and abort_event.is_set():
                    break
                try:
                    # exclude_from_context: UI/audit may keep them; model never sees them
                    model_messages = messages_for_model(messages)
                    msg = await chat(
                        messages=model_messages,
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
            if abort_event is not None and abort_event.is_set():
                terminal_status = "aborted"
                terminal_error = "aborted by user"
                yield {
                    "type": "error",
                    "status": "aborted",
                    "error": terminal_error,
                    "tool_call_log": tool_call_log,
                }
                return
            if msg is None:
                terminal_status = "failed"
                terminal_error = (
                    f"LLM error at step {step} after "
                    f"{config.llm_retry_max + 1} attempts: {last_err}"
                )
                await emit_audit(
                    audit_bus,
                    layer=AuditLayer.TURN,
                    phase=AuditPhase.END,
                    name=f"step_{step}",
                    payload={"status": "failed", "error": terminal_error},
                    agent_run_id=agent_run_id,
                    turn_id=turn_id,
                )
                yield {
                    "type": "error",
                    "status": "failed",
                    "error": terminal_error,
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
                    await emit_audit(
                        audit_bus,
                        layer=AuditLayer.TURN,
                        phase=AuditPhase.END,
                        name=f"step_{step}",
                        payload={"status": "auto_continue"},
                        agent_run_id=agent_run_id,
                        turn_id=turn_id,
                    )
                    continue
                await emit_audit(
                    audit_bus,
                    layer=AuditLayer.MESSAGE,
                    phase=AuditPhase.END,
                    name="assistant",
                    payload={"kind": "answer", "preview": (candidate_text or "")[:200]},
                    agent_run_id=agent_run_id,
                    turn_id=turn_id,
                )
                await emit_audit(
                    audit_bus,
                    layer=AuditLayer.TURN,
                    phase=AuditPhase.END,
                    name=f"step_{step}",
                    payload={"status": "answer_ready"},
                    agent_run_id=agent_run_id,
                    turn_id=turn_id,
                )
                terminal_status = "ok"
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
                await emit_audit(
                    audit_bus,
                    layer=AuditLayer.TOOL_EXECUTION,
                    phase=AuditPhase.START,
                    name=call.function.name,
                    payload={"arguments_preview": (call.function.arguments or "")[:200]},
                    agent_run_id=agent_run_id,
                    turn_id=turn_id,
                    tool_call_id=getattr(call, "id", None),
                )
                try:
                    out = await dispatch(call)
                finally:
                    await emit_audit(
                        audit_bus,
                        layer=AuditLayer.TOOL_EXECUTION,
                        phase=AuditPhase.END,
                        name=call.function.name,
                        payload={},
                        agent_run_id=agent_run_id,
                        turn_id=turn_id,
                        tool_call_id=getattr(call, "id", None),
                    )
                return out

            # INV-31: sequential by default; parallel only when every tool opts in
            if _should_run_parallel(
                tool_calls,
                default_mode=config.default_execution_mode,
                execution_mode_for=execution_mode_for,
            ):
                results = await asyncio.gather(
                    *[_dispatch_or_reflect(c) for c in tool_calls]
                )
            else:
                results = []
                for c in tool_calls:
                    results.append(await _dispatch_or_reflect(c))

            for call, raw in zip(tool_calls, results):
                tr = normalize_tool_result(raw)
                # Per-tool override via execution_mode_for metadata is future work;
                # config.tool_truncate_mode applies to the whole run (default tail).
                result_str = truncate_tool_result(
                    tr.for_model(),
                    max_chars=config.tool_result_max_chars,
                    max_lines=config.tool_result_max_lines,
                    mode=config.tool_truncate_mode or "tail",
                )
                tool_call_log.append(
                    {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                        "result_preview": result_str[:200],
                        "is_error": tr.is_error,
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
                    "error": tr.is_error,
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
                await emit_audit(
                    audit_bus,
                    layer=AuditLayer.TURN,
                    phase=AuditPhase.END,
                    name=f"step_{step}",
                    payload={"status": "budget"},
                    agent_run_id=agent_run_id,
                    turn_id=turn_id,
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
                    terminal_status = "error"
                    terminal_error = (
                        f"aborted: agent stuck in a tool-call loop "
                        f"(repeated identical calls); reflector gave up "
                        f"after {config.reflect_max} nudges"
                    )
                    await emit_audit(
                        audit_bus,
                        layer=AuditLayer.TURN,
                        phase=AuditPhase.END,
                        name=f"step_{step}",
                        payload={"status": "loop_abort"},
                        agent_run_id=agent_run_id,
                        turn_id=turn_id,
                    )
                    yield {
                        "type": "error",
                        "status": "error",
                        "error": terminal_error,
                        "tool_call_log": tool_call_log,
                    }
                    return
                messages.append({"role": "user", "content": config.reflect_guidance})

            await emit_audit(
                audit_bus,
                layer=AuditLayer.TURN,
                phase=AuditPhase.END,
                name=f"step_{step}",
                payload={"status": "tools_done", "tool_count": len(tool_calls)},
                agent_run_id=agent_run_id,
                turn_id=turn_id,
            )

        terminal_status = "error"
        terminal_error = f"exceeded tool_loop_max_steps ({config.max_steps})"
        yield {
            "type": "error",
            "status": "error",
            "error": terminal_error,
            "tool_call_log": tool_call_log,
        }
    finally:
        await emit_audit(
            audit_bus,
            layer=AuditLayer.AGENT,
            phase=AuditPhase.END,
            name=config.agent_name or "agent",
            payload={"status": terminal_status, "error": terminal_error},
            agent_run_id=agent_run_id,
        )
