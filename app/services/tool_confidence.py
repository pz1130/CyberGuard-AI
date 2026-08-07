"""Heuristic tool-call confidence for the gatekeeper (audit #10).

Nothing in the runtime previously produced a confidence value, so
``escalate_to_human_below`` was dead configuration. This estimator is
deliberately simple and deterministic: it maps taxonomy + argument sparseness
to a score in ``[0, 1]``. Callers that later have a model-supplied score can
override by passing their own value into ``gatekeeper_check``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

_BASE = {
    "observe": 0.92,
    "annotate": 0.90,
    "notify": 0.80,
    "contain_soft": 0.70,
    "contain_hard": 0.55,
    "remediate": 0.50,
    "mutate": 0.40,
}

_RISK_PENALTY = {
    "low": 0.0,
    "medium": 0.08,
    "high": 0.18,
    "critical": 0.28,
}

# Categories whose side effects make parallel execution unsafe by default.
SEQUENTIAL_CATEGORIES = frozenset({
    "contain_soft", "contain_hard", "remediate", "mutate", "notify",
})


def estimate_tool_confidence(
    tool_meta: Optional[Dict[str, Any]],
    args: Optional[Dict[str, Any]] = None,
) -> float:
    meta = tool_meta or {}
    cat = (meta.get("action_category") or "observe").lower()
    risk = (meta.get("risk_tier") or "low").lower()
    score = _BASE.get(cat, 0.75) - _RISK_PENALTY.get(risk, 0.05)
    if not args:
        score -= 0.10
    elif all(v in (None, "", [], {}) for v in args.values()):
        score -= 0.08
    return round(max(0.0, min(1.0, score)), 3)


def needs_sequential_execution(tool_meta: Optional[Dict[str, Any]]) -> bool:
    """Whether a tool must run alone (not inside asyncio.gather).

    Explicit ``execution_mode`` on the tool wins; otherwise derive from
    ``action_category`` (write/delete/network-effect categories are sequential).
    """
    meta = tool_meta or {}
    mode = (meta.get("execution_mode") or "").lower()
    if mode == "sequential":
        return True
    if mode == "parallel":
        return False
    cat = (meta.get("action_category") or "observe").lower()
    return cat in SEQUENTIAL_CATEGORIES
