"""Confidence estimation, so `escalate_to_human_below` stops being dead config.

`gatekeeper_check` escalates when confidence falls below the agent's
`escalate_to_human_below` threshold — but every call site passed None, so that
branch never ran and the setting was configurable, documented, and inert
(audit #10).

Deliberately deterministic: the score maps a tool's taxonomy plus argument
sparseness to [0, 1]. It is not read from the model's output, which would be
hostile-source input steering a gate (INV-39).
"""
import pytest

from app.services.tool_confidence import estimate_tool_confidence


def test_read_only_categories_score_higher_than_side_effecting_ones():
    observe = estimate_tool_confidence({"action_category": "observe"})
    contain = estimate_tool_confidence({"action_category": "contain_hard"})
    mutate = estimate_tool_confidence({"action_category": "mutate"})
    assert observe > contain > mutate


def test_a_higher_risk_tier_lowers_confidence():
    low = estimate_tool_confidence({"action_category": "observe", "risk_tier": "low"})
    crit = estimate_tool_confidence({"action_category": "observe", "risk_tier": "critical"})
    assert crit < low


def test_missing_arguments_lower_confidence():
    with_args = estimate_tool_confidence({"action_category": "observe"}, {"target": "10.0.0.1"})
    without = estimate_tool_confidence({"action_category": "observe"}, {})
    empty = estimate_tool_confidence({"action_category": "observe"}, {"target": ""})
    assert without < with_args
    assert empty < with_args


def test_the_score_stays_in_range_for_unknown_taxonomy():
    score = estimate_tool_confidence({"action_category": "no_such_category",
                                       "risk_tier": "no_such_tier"})
    assert 0.0 <= score <= 1.0


def test_untagged_tools_are_not_assumed_confident():
    """An untagged MCP tool is unknown, not safe."""
    untagged = estimate_tool_confidence({"action_category": None, "risk_tier": None})
    observe = estimate_tool_confidence({"action_category": "observe", "risk_tier": "low"})
    assert untagged < observe


@pytest.mark.asyncio
async def test_a_low_confidence_call_escalates_through_the_gate(monkeypatch):
    """The end the estimator exists for: the dead branch now fires."""
    from unittest.mock import AsyncMock
    from app.services.gatekeeper import Decision, gatekeeper_check
    from app.services.governance_config import load_governance

    monkeypatch.setattr("app.services.kill_switch.is_halted", AsyncMock(return_value=False))
    gov = load_governance({"autonomy_tier": "L3", "allowed_categories": ["mutate"],
                            "escalate_to_human_below": 0.95, "is_poc": False,
                            "agent_name": "x"})
    meta = {"action_category": "mutate", "risk_tier": "critical"}
    verdict = gatekeeper_check(meta, gov,
                                confidence=estimate_tool_confidence(meta, {}))
    assert verdict.decision is Decision.NEEDS_APPROVAL
    assert "confidence" in verdict.reason
