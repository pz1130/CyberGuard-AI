"""INV-13 · user-controlled text must not drive control-flow branches."""
from __future__ import annotations

import pytest

from app.agents.master import MasterAgent
from app.agents.states import MasterAgentState, AgentState


def _agent() -> MasterAgent:
    return MasterAgent(llm_router=None)


def test_route_group_chat_only_when_flag_set():
    m = _agent()
    assert m._route_decision({"group_chat_active": True, "task_plan": []}) == "group_chat"
    assert m._route_decision({"group_chat_active": False, "task_plan": []}) == "summarize_direct"


def test_validation_decision_uses_approval_required_not_failures():
    m = _agent()
    assert m._validation_decision({"approval_required": True, "validation_passed": True}) == "rejected"
    assert m._validation_decision({"approval_required": False, "validation_passed": False}) == "approved"
    assert m._validation_decision({"approval_required": False, "validation_passed": True}) == "approved"


@pytest.mark.asyncio
async def test_keyword_in_user_input_does_not_activate_group_chat(monkeypatch):
    """Embedding 'discuss' / 'all agents' in text must not flip group_chat_active."""
    async def noop_audit(**kwargs):
        return None

    monkeypatch.setattr("app.agents.master.log_audit", noop_audit)

    class Router:
        async def parse_intent(self, *a, **k):
            return {
                "intent": "task_execution",
                "task_plan": [],
                "reasoning": "normal",
            }

    m = MasterAgent(llm_router=Router())
    state: MasterAgentState = {
        "user_input": "Please discuss this with all agents in a group chat later",
        "user_id": 1,
        "mode": "normal",
        "group_chat_active": False,
    }
    out = await m._parse_intent_node(state)
    assert out.get("group_chat_active") is not True
    assert out.get("intent") == "task_execution"


@pytest.mark.asyncio
async def test_structured_group_chat_intent_activates(monkeypatch):
    async def noop_audit(**kwargs):
        return None

    monkeypatch.setattr("app.agents.master.log_audit", noop_audit)

    class Router:
        async def parse_intent(self, *a, **k):
            return {"intent": "group_chat", "task_plan": [], "reasoning": "gc"}

    m = MasterAgent(llm_router=Router())
    state: MasterAgentState = {
        "user_input": "anything",
        "user_id": 1,
        "mode": "normal",
    }
    out = await m._parse_intent_node(state)
    assert out.get("group_chat_active") is True


@pytest.mark.asyncio
async def test_critical_in_output_text_does_not_force_approval():
    """Free-text 'critical' in agent output must not set approval_required."""
    m = _agent()
    state: MasterAgentState = {
        "sub_results": {
            "1": {
                "status": "completed",
                "output": "Found critical vulnerability — immediate action required emergency",
            }
        },
        "task_plan": [],
        "approval_required": False,
        "current_state": AgentState.VALIDATE_RESULTS,
    }
    out = await m._validation_node(state)
    assert out.get("approval_required") is False
    assert out.get("validation_passed") is True


@pytest.mark.asyncio
async def test_structured_needs_approval_forces_hitl():
    m = _agent()
    state: MasterAgentState = {
        "sub_results": {
            "1": {"status": "needs_approval", "output": "waiting"},
        },
        "task_plan": [],
        "approval_required": False,
    }
    out = await m._validation_node(state)
    assert out.get("approval_required") is True
    assert m._validation_decision(out) == "rejected"


@pytest.mark.asyncio
async def test_structured_risk_level_forces_hitl():
    m = _agent()
    state: MasterAgentState = {
        "sub_results": {
            "1": {"status": "completed", "output": "ok", "risk_level": "critical"},
        },
        "task_plan": [],
    }
    out = await m._validation_node(state)
    assert out.get("approval_required") is True


@pytest.mark.asyncio
async def test_task_requires_approval_forces_hitl():
    m = _agent()
    state: MasterAgentState = {
        "sub_results": {"1": {"status": "completed", "output": "done"}},
        "task_plan": [{"agent_id": 1, "task": "x", "requires_approval": True}],
    }
    out = await m._validation_node(state)
    assert out.get("approval_required") is True
