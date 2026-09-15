"""The linchpin: run_python's needs_approval must reach the approval node.

D1 rests entirely on master.py picking up a needs_approval sub-result. If that
wiring ever changes, run_python would silently return "needs approval" to the
model and the graph would summarise instead of suspending — no approval, no
execution, no error.
"""
from __future__ import annotations

from app.agents.master import MasterAgent


def test_a_needs_approval_sub_result_routes_to_the_approval_node():
    state = {"approval_required": True, "approval_status": None}
    assert MasterAgent._validation_decision(MasterAgent, state) == "rejected"


def test_a_spent_approval_does_not_satisfy_the_next_gate():
    # approval_granted_round must equal the current round, or the first
    # approval in a thread would stand in for every later one.
    state = {
        "approval_required": True, "approval_status": "approved",
        "approval_granted_round": 0, "approval_round": 1,
    }
    assert MasterAgent._validation_decision(MasterAgent, state) == "rejected"


def test_a_current_approval_lets_the_run_continue():
    state = {
        "approval_required": True, "approval_status": "approved",
        "approval_granted_round": 1, "approval_round": 1,
    }
    assert MasterAgent._validation_decision(MasterAgent, state) == "approved"
