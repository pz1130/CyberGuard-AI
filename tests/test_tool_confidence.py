"""Confidence estimator + sequential-mode helpers (audit #10 / #15)."""
from app.services.tool_confidence import (
    estimate_tool_confidence,
    needs_sequential_execution,
)


def test_observe_has_high_confidence():
    c = estimate_tool_confidence({"action_category": "observe", "risk_tier": "low"},
                                 {"query": "x"})
    assert c >= 0.85


def test_remediate_has_lower_confidence_can_escalate():
    c = estimate_tool_confidence(
        {"action_category": "remediate", "risk_tier": "high"}, {})
    # Default escalate_to_human_below is 0.60 — this must land under it.
    assert c < 0.60


def test_mutate_is_sequential_by_default():
    assert needs_sequential_execution({"action_category": "mutate"}) is True
    assert needs_sequential_execution({"action_category": "observe"}) is False


def test_explicit_execution_mode_wins():
    assert needs_sequential_execution(
        {"action_category": "observe", "execution_mode": "sequential"}) is True
    assert needs_sequential_execution(
        {"action_category": "mutate", "execution_mode": "parallel"}) is False
