"""Phase-3 graph orchestration: checkpointer, interrupt, back edges, routing."""
import uuid

import pytest
from unittest.mock import AsyncMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.master import MasterAgent
from app.agents.states import AgentState


def _master(checkpointer=None):
    m = MasterAgent(llm_router=None, checkpointer=checkpointer or MemorySaver())
    return m


@pytest.mark.asyncio
async def test_validation_routes_approval_required_to_approval_node():
    m = _master()
    state = {
        "validation_passed": True,
        "approval_required": True,
        "approval_status": None,
        "replan_count": 0,
        "max_replans": 1,
    }
    assert m._validation_decision(state) == "needs_approval"


@pytest.mark.asyncio
async def test_validation_routes_failure_to_replan_then_final():
    m = _master()
    state = {
        "validation_passed": False,
        "approval_required": False,
        "replan_count": 0,
        "max_replans": 1,
    }
    assert m._validation_decision(state) == "replan"
    state["replan_count"] = 1
    assert m._validation_decision(state) == "failed_final"


@pytest.mark.asyncio
async def test_approval_decision_re_executes_needs_approval_tools():
    m = _master()
    state = {
        "approval_status": "approved",
        "sub_results": {"1": {"status": "needs_approval"}},
        "task_plan": [],
    }
    assert m._approval_decision(state) == "re_execute"
    state["sub_results"] = {"1": {"status": "completed", "output": "critical finding"}}
    state["task_plan"] = []
    assert m._approval_decision(state) == "summarize"
    state["approval_status"] = "rejected"
    assert m._approval_decision(state) == "rejected"


@pytest.mark.asyncio
async def test_interrupt_suspends_without_blocking_and_resume_continues():
    """#19/#20: approval uses interrupt(); resume finishes the graph."""
    cp = MemorySaver()

    async def fake_parse(state):
        state["task_plan"] = [{
            "agent_type": "remediation", "task": "block ip",
            "requires_approval": True,
        }]
        state["intent"] = "task_execution"
        return state

    m2 = MasterAgent(llm_router=None, checkpointer=cp)
    m2._parse_intent_node = fake_parse  # type: ignore
    # Avoid real LLM / network on the re-execute path after approval.
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "completed", "output": "blocked", "agent_id": 1,
    })
    m2._local_executor = local

    # The approval node now looks the request_id up before creating, so a
    # hardcoded id can collide with a leftover row in the shared test DB.
    run_id = f"req-test-{uuid.uuid4()}"

    with patch("app.services.approval_service.ApprovalService.create_request",
               new=AsyncMock(return_value=type("R", (), {"id": 42})())) as create, \
         patch("app.services.approval_service.ApprovalService.get_by_request_id",
               new=AsyncMock(return_value=None)), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted",
               new=AsyncMock(return_value=False)):

        suspended = await m2.run(
            user_input="block the ip",
            user_id=1,
            request_id=run_id,
            thread_id="thread-test-2",
        )

        assert suspended.get("interrupted") is True
        assert suspended.get("approval_status") == "pending"
        create.assert_awaited()

        resumed = await m2.resume(
            "thread-test-2", decision="approved", comment="lgtm", user_id=1,
        )

    assert resumed.get("interrupted") is not True
    assert resumed.get("approval_status") == "approved"
    assert resumed.get("current_state") == AgentState.END
    assert "blocked" in (resumed.get("final_summary") or "")


@pytest.mark.asyncio
async def test_validation_node_sets_risk_and_action_items():
    m = _master()
    state = await m._validation_node({
        "sub_results": {
            "scan": {"status": "completed",
                     "output": "CRITICAL vulnerability found. Recommendation: patch now."},
        },
    })
    assert state["validation_passed"] is True
    assert state["approval_required"] is True
    assert state["risk_score"] is not None
    assert state["action_items"]


@pytest.mark.asyncio
async def test_toolnode_import_removed():
    """#22: unused ToolNode import must stay gone."""
    import ast
    import pathlib
    src = pathlib.Path("app/agents/master.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "prebuilt" in node.module:
            names = [a.name for a in node.names]
            assert "ToolNode" not in names
