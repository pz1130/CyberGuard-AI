"""Heuristic tool-call confidence for the gatekeeper (audit #10).

``gatekeeper_check`` escalates to a human when confidence falls below the
agent's ``escalate_to_human_below``, but nothing in the runtime ever produced a
confidence value — every call site passed ``None``, so that branch never ran
and the setting was configurable, documented, and inert.

The estimate is deliberately simple and deterministic: it maps a tool's
taxonomy plus argument sparseness to a score in ``[0, 1]``. It is emphatically
**not** derived from model or tool output — that would let hostile-source
content steer a gate (INV-39). A caller that later has a genuine model-supplied
score can pass its own value into ``gatekeeper_check`` instead.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Read-only work is the safest thing an agent does; the further a category
# moves toward irreversible side effects, the less a heuristic should vouch
# for it unsupervised.
_BASE = {
    "observe": 0.92,
    "annotate": 0.90,
    "notify": 0.80,
    "contain_soft": 0.70,
    "contain_hard": 0.55,
    "remediate": 0.50,
    "mutate": 0.40,
}
# An untagged tool is *unknown*, not safe — it must not score above a tool an
# operator actually classified as read-only.
_UNTAGGED = 0.75

_RISK_PENALTY = {"low": 0.0, "medium": 0.08, "high": 0.18, "critical": 0.28}
_UNKNOWN_RISK_PENALTY = 0.05


def estimate_tool_confidence(
    tool_meta: Optional[Dict[str, Any]],
    args: Optional[Dict[str, Any]] = None,
) -> float:
    """Confidence in ``[0, 1]`` that this call is safe to run unsupervised."""
    meta = tool_meta or {}
    category = (meta.get("action_category") or "").lower()
    risk = (meta.get("risk_tier") or "").lower()

    score = _BASE.get(category, _UNTAGGED)
    score -= _RISK_PENALTY.get(risk, _UNKNOWN_RISK_PENALTY)

    # A call with no arguments, or with every argument blank, is usually the
    # model guessing at a signature rather than acting on something it knows.
    if not args:
        score -= 0.10
    elif all(v in (None, "", [], {}) for v in args.values()):
        score -= 0.08

    return round(max(0.0, min(1.0, score)), 3)
