"""tool_call_budget defaults track max_steps (audit #4)."""
from app.services.internal_agent import InternalAgentRunner


def test_default_budget_is_bounded_by_max_steps():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "t", "tool_loop_max_steps": 8,
        "permission_level": "medium",
    })
    # Previously defaulted to 100 and was unreachable under 8 steps.
    assert runner.tool_call_budget <= 8 * 5
    assert runner.tool_call_budget >= 16


def test_explicit_budget_wins():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "t", "tool_loop_max_steps": 8,
        "tool_call_budget": 3,
    })
    assert runner.tool_call_budget == 3


def test_low_permission_budget_is_tighter():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "t", "tool_loop_max_steps": 8,
        "permission_level": "low",
    })
    assert runner.tool_call_budget <= 8 * 3
