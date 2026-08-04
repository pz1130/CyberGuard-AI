"""INV-23 · fan-out gate unit tests."""
from __future__ import annotations

from app.services.fanout_gate import FanoutLimits, apply_fanout_gates


def test_plan_size_cap():
    limits = FanoutLimits(max_plan_size=2, max_per_agent=10, require_target=False)
    plan = [
        {"agent_id": 1, "task": "a"},
        {"agent_id": 2, "task": "b"},
        {"agent_id": 3, "task": "c"},
    ]
    d = apply_fanout_gates(plan, limits=limits)
    assert len(d.accepted) == 2
    assert len(d.rejected) == 1
    assert "plan size" in d.rejected[0]["reason"]


def test_per_agent_cap():
    limits = FanoutLimits(max_plan_size=10, max_per_agent=1, require_target=False)
    plan = [
        {"agent_id": 1, "task": "a"},
        {"agent_id": 1, "task": "b"},
        {"agent_id": 2, "task": "c"},
    ]
    d = apply_fanout_gates(plan, limits=limits)
    assert len(d.accepted) == 2
    assert any("per-agent" in r["reason"] for r in d.rejected)


def test_agent_type_counts_as_target():
    """Intent parser routes by agent_type — must still pass require_target."""
    limits = FanoutLimits(require_target=True, max_plan_size=10)
    plan = [{"agent_type": "threat_intel", "task": "scan"}]
    d = apply_fanout_gates(plan, limits=limits)
    assert len(d.accepted) == 1


def test_unspecified_target_rejected():
    limits = FanoutLimits(require_target=True, max_plan_size=10)
    plan = [{"task": "do something vague"}]
    d = apply_fanout_gates(plan, limits=limits)
    assert d.accepted == []
    assert "unspecified target" in d.rejected[0]["reason"]


def test_depth_exceeded_rejects_all():
    limits = FanoutLimits(max_depth=1)
    plan = [{"agent_id": 1, "task": "x"}]
    d = apply_fanout_gates(plan, limits=limits, dispatch_depth=2)
    assert d.accepted == []
    assert len(d.rejected) == 1
    assert "dispatch_depth" in d.rejected[0]["reason"]


def test_depth_at_limit_ok():
    limits = FanoutLimits(max_depth=1, require_target=True)
    plan = [{"agent_id": 1, "task": "x"}]
    d = apply_fanout_gates(plan, limits=limits, dispatch_depth=1)
    assert len(d.accepted) == 1
