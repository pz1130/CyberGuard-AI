"""A post-approval re-entry must not re-run work that already succeeded.

`approval_node --re_execute--> sub_agent_executor_node` re-enters the node that
performs every tool call. Without this, a sibling task that finished in the
first pass runs a second time on resume and its tools take effect twice — a
duplicate scan, a duplicate notification, a duplicate containment action.

This was dormant until a gated tool's needs_approval started reaching the graph
(`3905ee8`); before that the internal-agent path routed to `summarize` and the
node was never re-entered.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agents.master import MasterAgent, tasks_needing_dispatch


def _agent():
    return MasterAgent(llm_router=None, checkpointer=MemorySaver())


PLAN = [
    {"agent_type": "recon", "task": "scan the host", "dispatch_source": "user_explicit"},
    {"agent_type": "remediation", "task": "block ip", "dispatch_source": "user_explicit"},
]


# --- the decision, on its own ---

def test_everything_is_dispatched_on_a_first_pass():
    assert tasks_needing_dispatch(PLAN, {}) == PLAN


def test_a_completed_task_is_not_dispatched_again():
    prior = {"recon": {"status": "completed", "output": "3 open ports"}}
    assert tasks_needing_dispatch(PLAN, prior) == [PLAN[1]]


def test_a_task_that_asked_for_approval_is_dispatched_again():
    # That is the whole point of the re-entry.
    prior = {"remediation": {"status": "needs_approval", "output": None}}
    assert tasks_needing_dispatch(PLAN, prior) == PLAN


@pytest.mark.parametrize("status", ["failed", "denied", "error", "halted"])
def test_an_unsuccessful_task_is_dispatched_again(status):
    prior = {"recon": {"status": status, "output": None}}
    assert tasks_needing_dispatch(PLAN, prior) == PLAN


def test_an_explicit_agent_id_keys_the_result():
    plan = [{"agent_id": 7, "agent_type": "recon", "task": "x"}]
    assert tasks_needing_dispatch(plan, {"7": {"status": "completed"}}) == []


def test_an_agent_name_keys_the_result_when_there_is_no_id():
    plan = [{"agent_name": "scanner", "agent_type": "recon", "task": "x"}]
    assert tasks_needing_dispatch(plan, {"scanner": {"status": "completed"}}) == []


def test_an_unmatched_key_is_dispatched_rather_than_skipped():
    # Degrading to the old behaviour is safe; skipping work that never ran is not.
    prior = {"something-else": {"status": "completed"}}
    assert tasks_needing_dispatch(PLAN, prior) == PLAN


def test_a_non_dict_result_does_not_crash_the_decision():
    assert tasks_needing_dispatch(PLAN, {"recon": "not a dict"}) == PLAN


# --- the node honours it ---

@pytest.mark.asyncio
async def test_re_entry_does_not_re_run_a_completed_sibling():
    m = _agent()
    dispatched = []

    async def record(agent_id=None, task=None, user_id=None, context=None, **_kw):
        dispatched.append(task)
        return {"status": "completed", "output": "done", "agent_id": agent_id}

    local = AsyncMock()
    local.execute = AsyncMock(side_effect=record)
    m._local_executor = local

    state = {
        "task_plan": PLAN,
        "user_id": 1,
        "request_id": "req-replay",
        # First pass finished recon; remediation stopped for approval.
        "sub_results": {
            "recon": {"status": "completed", "output": "3 open ports"},
            "remediation": {"status": "needs_approval", "output": None},
        },
        "pre_approved": True,
        "approval_status": "approved",
        "approval_round": 0,
        "approval_granted_round": 0,
    }

    with patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted", new=AsyncMock(return_value=False)):
        out = await m._sub_agent_executor_node(state)

    assert "scan the host" not in dispatched, (
        "recon already succeeded; re-running it repeats its tool calls"
    )
    # The earlier result is still there for the summariser to use.
    assert out["sub_results"]["recon"]["output"] == "3 open ports"
