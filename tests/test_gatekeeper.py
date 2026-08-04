"""Tests for the pure gatekeeper decision module."""
from app.services.gatekeeper import gatekeeper_check, Decision, GovernanceContext

OBSERVE = dict(action_category="observe", risk_tier="low")
HARD = dict(action_category="contain_hard", risk_tier="high", has_rollback=True)
MUTATE = dict(action_category="mutate", risk_tier="critical")


def ctx(**kw):
    base = dict(autonomy_tier="L2",
                allowed_categories=["observe", "annotate", "notify", "contain_soft", "contain_hard"],
                escalate_below=0.60, is_poc=True, halted=False, external_unwrapped=False)
    base.update(kw)
    return GovernanceContext(**base)


def test_observe_allowed():
    assert gatekeeper_check(OBSERVE, ctx(), confidence=0.9).decision is Decision.ALLOW


def test_mutate_denied_in_poc():
    r = gatekeeper_check(MUTATE, ctx(allowed_categories=["mutate"]), confidence=0.99)
    assert r.decision is Decision.DENY and "poc" in r.reason.lower()


def test_category_not_allowed_denied():
    r = gatekeeper_check(HARD, ctx(allowed_categories=["observe"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_contain_hard_needs_approval():
    assert gatekeeper_check(HARD, ctx(), confidence=0.99).decision is Decision.NEEDS_APPROVAL


def test_low_confidence_escalates():
    assert gatekeeper_check(OBSERVE, ctx(), confidence=0.4).decision is Decision.NEEDS_APPROVAL


def test_autonomy_ceiling_blocks_remediate_for_l2():
    r = gatekeeper_check(dict(action_category="remediate", risk_tier="high", has_rollback=True),
                         ctx(autonomy_tier="L1", allowed_categories=["remediate"]), confidence=0.99)
    assert r.decision is Decision.DENY


def test_halt_denies_everything():
    r = gatekeeper_check(OBSERVE, ctx(halted=True), confidence=0.99)
    assert r.decision is Decision.DENY and "halt" in r.reason.lower()


def test_envelope_action_without_rollback_denied():
    r = gatekeeper_check(
        {"action_category": "contain_hard", "risk_tier": "high", "has_rollback": False},
        ctx(), confidence=0.99)
    assert r.decision is Decision.DENY and "rollback" in r.reason.lower()


def test_envelope_action_with_rollback_needs_approval():
    r = gatekeeper_check(
        {"action_category": "contain_hard", "risk_tier": "high", "has_rollback": True},
        ctx(), confidence=0.99)
    assert r.decision is Decision.NEEDS_APPROVAL


def test_external_unwrapped_blocked_from_state_change():
    r = gatekeeper_check({"action_category": "contain_soft", "risk_tier": "low", "has_rollback": True},
                         ctx(external_unwrapped=True), confidence=0.99)
    assert r.decision is Decision.DENY and "wrapped" in r.reason.lower()


def test_external_unwrapped_allowed_readonly():
    r = gatekeeper_check({"action_category": "observe", "risk_tier": "low"},
                         ctx(external_unwrapped=True), confidence=0.99)
    assert r.decision is Decision.ALLOW
