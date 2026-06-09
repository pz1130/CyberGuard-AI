"""Declarative agent governance (NDB Std §B1 / A1 / A3).

Single source of truth for an agent's governance, replacing the temporary
metadata_json default-reading. Builds the GovernanceContext the gatekeeper
consumes, exports the Standard's agent_governance.yaml, and maps risk tier to
the required approver.
"""
from __future__ import annotations
import yaml
from app.services.gatekeeper import GovernanceContext

DEFAULT_ALLOWED = ["observe", "annotate", "notify", "contain_soft"]

_RISK_APPROVER = {
    "critical": {"label": "Security Director + Legal", "min_role": "admin",   "needs_approval": True},
    "high":     {"label": "SOC Manager",               "min_role": "admin",   "needs_approval": True},
    "medium":   {"label": "Senior SOC Analyst",        "min_role": "analyst", "needs_approval": True},
    "low":      {"label": "Agent operator (logged)",   "min_role": None,      "needs_approval": False},
}
_ROLE_RANK = {"viewer": 0, "auditor": 0, "analyst": 1, "operator": 2, "admin": 3}


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def validate_autonomy(tier: str, l3_ref: str | None) -> None:
    t = (tier or "L2").upper()
    if t == "L4":
        raise ValueError("Autonomy tier L4 (fully autonomous) is forbidden by the Standard.")
    if t == "L3" and not l3_ref:
        raise ValueError("Autonomy tier L3 requires a prior Chief of IT authorization reference.")


def load_governance(agent) -> GovernanceContext:
    cats = _get(agent, "allowed_categories")
    return GovernanceContext(
        autonomy_tier=_get(agent, "autonomy_tier", "L2") or "L2",
        allowed_categories=cats if cats else list(DEFAULT_ALLOWED),
        escalate_below=float(_get(agent, "escalate_to_human_below", 0.60) or 0.60),
        is_poc=bool(_get(agent, "is_poc", True)),
        halted=False,
    )


def approver_for_risk(risk_tier: str | None) -> dict:
    return _RISK_APPROVER.get((risk_tier or "low").lower(), _RISK_APPROVER["low"])


def role_meets(role: str | None, min_role: str | None) -> bool:
    if not min_role:
        return True
    return _ROLE_RANK.get((role or "viewer").lower(), 0) >= _ROLE_RANK[min_role]


def export_yaml(agent) -> str:
    cats = _get(agent, "allowed_categories") or DEFAULT_ALLOWED
    doc = {
        "agent_name": _get(agent, "agent_name"),
        "autonomy_tier": _get(agent, "autonomy_tier", "L2"),
        "allowed_actions": list(cats),
        "requires_approval": _get(agent, "requires_approval_rules") or [],
        "auto_execute_min_confidence": float(_get(agent, "auto_execute_min_confidence", 0.85) or 0.85),
        "escalate_to_human_below": float(_get(agent, "escalate_to_human_below", 0.60) or 0.60),
        "pii_handling_policy": _get(agent, "pii_handling_policy", "redact"),
        "audit_log_path": _get(agent, "audit_log_path") or "db://audit_logs",
        "kill_switch_enabled": bool(_get(agent, "kill_switch_enabled", True)),
    }
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)
