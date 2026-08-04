"""INV-23 · Server fan-out gates.

Caps plan size, per-agent multiplicity, nesting depth, and optional
require-named-target. Pure functions — master applies them before execute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FanoutLimits:
    max_plan_size: int = 12
    max_per_agent: int = 2
    max_depth: int = 1
    max_concurrent: int = 4
    # Reject tasks with no agent_id, agent_name, *or* agent_type (INV-23).
    # agent_type alone is allowed — that is how the intent parser routes today.
    require_target: bool = True


@dataclass
class FanoutDecision:
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    # rejected items are {task, reason}


def _target_key(task: Dict[str, Any]) -> str:
    if task.get("agent_id") is not None and str(task.get("agent_id")).strip() != "":
        return f"id:{task.get('agent_id')}"
    if task.get("agent_name"):
        return f"name:{task.get('agent_name')}"
    return f"type:{task.get('agent_type') or 'general'}"


def _has_target(task: Dict[str, Any]) -> bool:
    """True if the task names *some* dispatch target (id, name, or type)."""
    if task.get("agent_id") is not None and str(task.get("agent_id")).strip() != "":
        return True
    if task.get("agent_name") and str(task.get("agent_name")).strip():
        return True
    if task.get("agent_type") and str(task.get("agent_type")).strip():
        return True
    return False


def apply_fanout_gates(
    task_plan: List[Dict[str, Any]],
    *,
    limits: FanoutLimits,
    dispatch_depth: int = 0,
) -> FanoutDecision:
    """Filter a task_plan. Order preserved among accepted tasks."""
    decision = FanoutDecision()
    if dispatch_depth > limits.max_depth:
        for t in task_plan:
            decision.rejected.append(
                {
                    "task": t,
                    "reason": (
                        f"dispatch_depth {dispatch_depth} exceeds "
                        f"max_depth {limits.max_depth}"
                    ),
                }
            )
        return decision

    per_agent: Dict[str, int] = {}
    for t in task_plan:
        if not isinstance(t, dict):
            decision.rejected.append({"task": t, "reason": "task is not a dict"})
            continue
        if limits.require_target and not _has_target(t):
            decision.rejected.append(
                {
                    "task": t,
                    "reason": "unspecified target (need agent_id, agent_name, or agent_type)",
                }
            )
            continue
        if len(decision.accepted) >= limits.max_plan_size:
            decision.rejected.append(
                {
                    "task": t,
                    "reason": f"plan size cap {limits.max_plan_size}",
                }
            )
            continue
        key = _target_key(t)
        count = per_agent.get(key, 0)
        if count >= limits.max_per_agent:
            decision.rejected.append(
                {
                    "task": t,
                    "reason": f"per-agent cap {limits.max_per_agent} for {key}",
                }
            )
            continue
        per_agent[key] = count + 1
        decision.accepted.append(t)
    return decision


def limits_from_settings(settings: Any) -> FanoutLimits:
    return FanoutLimits(
        max_plan_size=int(getattr(settings, "SUB_AGENT_MAX_PLAN_SIZE", 12)),
        max_per_agent=int(getattr(settings, "SUB_AGENT_MAX_PER_AGENT", 2)),
        max_depth=int(getattr(settings, "SUB_AGENT_MAX_DEPTH", 1)),
        max_concurrent=int(getattr(settings, "SUB_AGENT_MAX_CONCURRENT", 4)),
        require_target=bool(
            getattr(
                settings,
                "SUB_AGENT_REQUIRE_TARGET",
                getattr(settings, "SUB_AGENT_REQUIRE_NAMED_TARGET", True),
            )
        ),
    )
