"""Tests for governance_config service."""
import pytest
from types import SimpleNamespace
from app.services import governance_config as gc
from app.services.gatekeeper import GovernanceContext

DEFAULT_CATS = ["observe", "annotate", "notify", "contain_soft"]


def _agent(**kw):
    base = dict(agent_name="threat_intel", autonomy_tier="L2", allowed_categories=None,
                auto_execute_min_confidence=0.85, escalate_to_human_below=0.60,
                pii_handling_policy="redact", kill_switch_enabled=True, is_poc=True,
                requires_approval_rules=None, l3_authorization_ref=None,
                associated_tools=[], audit_log_path=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_load_governance_applies_defaults():
    ctx = gc.load_governance(_agent())
    assert isinstance(ctx, GovernanceContext)
    assert ctx.autonomy_tier == "L2"
    assert ctx.allowed_categories == DEFAULT_CATS
    assert ctx.escalate_below == 0.60
    assert ctx.is_poc is True


def test_load_governance_respects_explicit_categories():
    ctx = gc.load_governance(_agent(allowed_categories=["observe", "contain_hard"]))
    assert ctx.allowed_categories == ["observe", "contain_hard"]


def test_validate_autonomy_rejects_l4():
    with pytest.raises(ValueError, match="L4"):
        gc.validate_autonomy("L4", l3_ref=None)


def test_validate_autonomy_l3_requires_ref():
    with pytest.raises(ValueError, match="Chief of IT"):
        gc.validate_autonomy("L3", l3_ref=None)
    gc.validate_autonomy("L3", l3_ref="CIO-2026-014")


def test_export_yaml_matches_appendix_b_shape():
    y = gc.export_yaml(_agent(agent_name="ir_agent", autonomy_tier="L2"))
    import yaml
    d = yaml.safe_load(y)
    assert d["agent_name"] == "ir_agent"
    assert d["autonomy_tier"] == "L2"
    for key in ("allowed_actions", "auto_execute_min_confidence",
                "escalate_to_human_below", "pii_handling_policy",
                "kill_switch_enabled", "audit_log_path"):
        assert key in d


def test_approver_for_risk_mapping():
    assert gc.approver_for_risk("critical")["min_role"] == "admin"
    assert gc.approver_for_risk("medium")["min_role"] == "analyst"
    assert gc.approver_for_risk("low")["needs_approval"] is False
