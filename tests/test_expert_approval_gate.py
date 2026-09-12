"""Expert mode must still open the pre-dispatch HITL gate for high-risk work.

Fan-out (INV-21) is not a safety exemption: `requires_approval` was hardcoded
False, so expert runs skipped the approval node until a tool came back
`needs_approval`. Advisory expert runs should still dispatch immediately.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.master import MasterAgent, plan_requires_approval
from app.agents.states import MasterAgentState


def _router(plan, intent="task_execution"):
    r = AsyncMock()
    r.parse_intent = AsyncMock(return_value={"intent": intent, "task_plan": plan})
    return r


class _Result:
    def __init__(self, agents):
        self._agents = agents

    def scalars(self):
        return self

    def all(self):
        return self._agents


class _Session:
    def __init__(self, agents):
        self._agents = agents

    async def execute(self, *_a, **_k):
        return _Result(self._agents)


class _Ctx:
    def __init__(self, agents):
        self._agents = agents

    async def __aenter__(self):
        return _Session(self._agents)

    async def __aexit__(self, *_a):
        return False


def _agents(*names):
    return [
        SimpleNamespace(id=i + 1, agent_name=name, backend_type="internal")
        for i, name in enumerate(names)
    ]


async def _parse(mode, user_input, agents, plan):
    m = MasterAgent(llm_router=_router(plan))
    with patch("app.core.database.get_db_context", lambda: _Ctx(agents)), \
         patch("app.agents.master.log_audit", AsyncMock()):
        state: MasterAgentState = {
            "user_input": user_input,
            "mode": mode,
            "user_id": 5,
        }
        return await m._parse_intent_node(state), m


def test_plan_requires_approval_from_flag_or_remediation_type():
    assert plan_requires_approval([]) is False
    assert plan_requires_approval([{"agent_type": "threat_intel"}]) is False
    assert plan_requires_approval([{"requires_approval": True}]) is True
    assert plan_requires_approval([{"agent_type": "remediation"}]) is True


@pytest.mark.asyncio
async def test_expert_with_agents_high_risk_pauses_before_dispatch():
    state, m = await _parse(
        "expert",
        "block 203.0.113.44 on the production edge",
        _agents("threat_intel", "remediation"),
        [{"agent_type": "remediation", "task": "block ip", "requires_approval": True}],
    )
    assert state["intent"] == "task_execution"
    assert len(state["task_plan"]) == 2
    assert all(t["dispatch_source"] == "user_expert" for t in state["task_plan"])
    assert all(t["requires_approval"] is True for t in state["task_plan"])
    assert m._route_decision(state) == "approval"


@pytest.mark.asyncio
async def test_expert_with_agents_advisory_still_fans_out_without_pre_gate():
    state, m = await _parse(
        "expert",
        "rank these alerts, do not contain",
        _agents("threat_intel", "log_anomaly"),
        [{"agent_type": "threat_intel", "task": "rank", "requires_approval": False}],
    )
    assert all(t["requires_approval"] is False for t in state["task_plan"])
    assert m._route_decision(state) == "sub_agents"


@pytest.mark.asyncio
async def test_expert_no_agents_high_risk_keeps_parser_plan_for_hitl():
    state, m = await _parse(
        "expert",
        "isolate backup-server and wipe snapshots",
        [],
        [{"agent_type": "remediation", "task": "wipe", "requires_approval": True}],
    )
    assert state.get("expert_mode_no_agents") is True
    assert state["task_plan"]
    assert state["task_plan"][0]["requires_approval"] is True
    assert m._route_decision(state) == "approval"


@pytest.mark.asyncio
async def test_expert_parser_failure_fails_closed_before_fan_out():
    router = _router([])
    router.parse_intent.side_effect = RuntimeError("provider unavailable")
    m = MasterAgent(llm_router=router)
    with patch("app.core.database.get_db_context", lambda: _Ctx(_agents("remediation"))), \
         patch("app.agents.master.log_audit", AsyncMock()):
        state: MasterAgentState = {
            "user_input": "isolate the host",
            "mode": "expert",
            "user_id": 5,
        }
        state = await m._parse_intent_node(state)

    assert state["task_plan"][0]["requires_approval"] is True
    assert m._route_decision(state) == "approval"
