"""Pure action-gatekeeper decision logic (NDB Std §Action Gatekeeper).

No I/O — takes a tool's taxonomy + a GovernanceContext + confidence and returns
ALLOW / DENY / NEEDS_APPROVAL with a reason. Wired into execute_tool().
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

ALWAYS_ALLOWED = {"observe", "annotate"}
APPROVAL_DEFAULT = {"contain_hard", "remediate"}
FORBIDDEN_IN_POC = {"mutate"}
RATE_LIMITED = {"notify"}

_MIN_TIER = {
    "observe": 0, "annotate": 0, "notify": 1, "contain_soft": 2,
    "contain_hard": 2, "remediate": 3, "mutate": 3,
}


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class GovernanceContext:
    autonomy_tier: str = "L2"
    allowed_categories: list[str] = field(default_factory=list)
    escalate_below: float = 0.60
    is_poc: bool = True
    halted: bool = False


@dataclass
class GatekeeperResult:
    decision: Decision
    reason: str
    category: str | None = None
    risk_tier: str | None = None


def _tier_num(t: str) -> int:
    try:
        return int(str(t).lstrip("Ll"))
    except ValueError:
        return 2


def gatekeeper_check(tool_meta: dict, gov: GovernanceContext, *, confidence: float | None) -> GatekeeperResult:
    cat = (tool_meta.get("action_category") or "observe").lower()
    risk = (tool_meta.get("risk_tier") or "low").lower()
    R = lambda d, why: GatekeeperResult(d, why, cat, risk)  # noqa: E731

    if gov.halted:
        return R(Decision.DENY, "kill switch / halt engaged")
    if gov.is_poc and cat in FORBIDDEN_IN_POC:
        return R(Decision.DENY, f"category '{cat}' is forbidden in a POC")
    if cat not in ALWAYS_ALLOWED and cat not in gov.allowed_categories:
        return R(Decision.DENY, f"category '{cat}' not in agent allowed_actions")
    if _tier_num(gov.autonomy_tier) < _MIN_TIER.get(cat, 2):
        return R(Decision.DENY, f"autonomy {gov.autonomy_tier} below minimum for '{cat}'")
    ENVELOPE = {"contain_soft", "contain_hard", "remediate"}
    if cat in ENVELOPE and not tool_meta.get("has_rollback", False):
        return R(Decision.DENY, f"category '{cat}' requires a registered rollback procedure")
    if cat in APPROVAL_DEFAULT:
        return R(Decision.NEEDS_APPROVAL, f"category '{cat}' requires human approval")
    if confidence is not None and confidence < gov.escalate_below:
        return R(Decision.NEEDS_APPROVAL, f"confidence {confidence:.2f} below {gov.escalate_below:.2f}")
    return R(Decision.ALLOW, "passed gatekeeper")
