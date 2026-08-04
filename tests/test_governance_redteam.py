"""Red-team governance tests — every forbidden path must be blocked.
Machine-checkable evidence for the POC 'Governance test results' deliverable."""
import pytest
from app.services.gatekeeper import gatekeeper_check, Decision, GovernanceContext
from app.core import pii


def _ctx(**kw):
    base = dict(autonomy_tier="L2",
                allowed_categories=["observe", "annotate", "notify", "contain_soft", "contain_hard"],
                escalate_below=0.60, is_poc=True, halted=False)
    base.update(kw)
    return GovernanceContext(**base)


def test_redteam_mutate_blocked_in_poc():
    r = gatekeeper_check({"action_category": "mutate", "risk_tier": "critical"},
                         _ctx(allowed_categories=["mutate"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_action_above_autonomy_blocked():
    r = gatekeeper_check({"action_category": "remediate", "risk_tier": "high", "has_rollback": True},
                         _ctx(autonomy_tier="L1", allowed_categories=["remediate"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_contain_without_rollback_blocked():
    r = gatekeeper_check({"action_category": "contain_hard", "risk_tier": "high", "has_rollback": False},
                         _ctx(), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_low_confidence_escalated():
    r = gatekeeper_check({"action_category": "contain_soft", "risk_tier": "low", "has_rollback": True},
                         _ctx(), confidence=0.30)
    assert r.decision is Decision.NEEDS_APPROVAL


def test_redteam_halt_blocks_everything():
    r = gatekeeper_check({"action_category": "observe", "risk_tier": "low"},
                         _ctx(halted=True), confidence=0.99)
    assert r.decision is Decision.DENY


def test_redteam_secret_blocked_before_llm():
    with pytest.raises(pii.SecretsDetectedError):
        pii.apply_policy("use AKIAIOSFODNN7EXAMPLE now", policy="redact")


def test_redteam_pii_redacted_before_llm():
    out, findings = pii.apply_policy("ping me at red@team.com", policy="redact")
    assert "red@team.com" not in out and findings
