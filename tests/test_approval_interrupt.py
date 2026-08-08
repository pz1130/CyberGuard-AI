"""Human approval suspends the graph instead of holding a worker, and one
decision authorises exactly one dispatch.

Four failures this pins down:

1. ``_approval_node`` polled a fresh DB session every 2s for up to an hour,
   holding one of four API workers for the whole wait.
2. Approving never let the action run — ``pre_approved`` reached no executor,
   so the re-dispatch hit the same refusal and the run summarised itself.
3. A second gated action in one run was waved through, because a bare
   ``approval_status == "approved"`` persisted for the life of the thread.
4. ``interrupt()`` discards the node's own writes, so a state-flag "create
   once" guard is always empty on resume and every approved run left a
   dangling pending approval behind.
"""
import uuid

import pytest
from unittest.mock import AsyncMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.master import MasterAgent, approval_request_id
from app.agents.states import AgentState


def _agent(checkpointer=None):
    return MasterAgent(llm_router=None, checkpointer=checkpointer or MemorySaver())


def _gated_plan():
    async def fake_parse(state):
        state["task_plan"] = [{
            "agent_type": "remediation", "task": "block ip",
            "requires_approval": True, "dispatch_source": "user_explicit",
        }]
        state["intent"] = "task_execution"
        return state
    return fake_parse


def _store_backed_approval_service(store):
    async def create(*, request_id, **kwargs):
        rec = type("R", (), {"id": len(store) + 1, "request_id": request_id})()
        store[request_id] = {"record": rec, "payload": kwargs.get("payload") or {}}
        return rec

    async def get(request_id):
        entry = store.get(request_id)
        return entry["record"] if entry else None

    return AsyncMock(side_effect=create), AsyncMock(side_effect=get)


# ---- request id ------------------------------------------------------------

def test_per_round_request_ids_fit_the_column_and_are_deterministic():
    """approval_requests.request_id is String(36); a suffixed uuid overflows."""
    run_id = "5f8c1b3e-9a2d-4f61-8b7c-0d1e2f3a4b5c"
    assert approval_request_id(run_id, 0) == run_id
    for rnd in (1, 2, 17):
        rid = approval_request_id(run_id, rnd)
        assert len(rid) <= 36, rid
        assert rid != run_id
        assert rid == approval_request_id(run_id, rnd)
    assert approval_request_id(run_id, 1) != approval_request_id(run_id, 2)


# ---- suspend / resume ------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_suspends_the_graph_and_resume_finishes_it():
    cp = MemorySaver()
    m = _agent(cp)
    m._parse_intent_node = _gated_plan()
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "completed", "output": "blocked", "agent_id": 1})
    m._local_executor = local

    store = {}
    create, get = _store_backed_approval_service(store)
    thread = f"thread-{uuid.uuid4()}"

    with patch("app.services.approval_service.ApprovalService.create_request", new=create), \
         patch("app.services.approval_service.ApprovalService.get_by_request_id", new=get), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted", new=AsyncMock(return_value=False)):

        suspended = await m.run(user_input="block the ip", user_id=1,
                                request_id=str(uuid.uuid4()), thread_id=thread)
        assert suspended.get("interrupted") is True
        assert suspended.get("approval_status") == "pending"

        resumed = await m.resume(thread, decision="approved", comment="ok", user_id=1)

    assert resumed.get("interrupted") is not True
    assert resumed.get("approval_status") == "approved"
    assert resumed.get("current_state") == AgentState.END
    # One approval opened, not one per graph entry.
    assert create.await_count == 1, list(store)


@pytest.mark.asyncio
async def test_the_approval_record_states_which_kind_of_approval_it_is():
    """INV-06 / INV-38: a self-approval must never read as separation of duties."""
    m = _agent()
    m._parse_intent_node = _gated_plan()
    m._local_executor = AsyncMock()

    store = {}
    create, get = _store_backed_approval_service(store)

    with patch("app.services.approval_service.ApprovalService.create_request", new=create), \
         patch("app.services.approval_service.ApprovalService.get_by_request_id", new=get), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted", new=AsyncMock(return_value=False)):
        await m.run(user_input="block the ip", user_id=1,
                    request_id=str(uuid.uuid4()), thread_id=f"thread-{uuid.uuid4()}")

    payload = next(iter(store.values()))["payload"]
    assert payload.get("approval_type") == "separation_of_duties"


# ---- one decision, one dispatch -------------------------------------------

@pytest.mark.asyncio
async def test_a_spent_decision_does_not_authorise_the_next_gate():
    m = _agent()
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "needs_approval", "output": None,
        "error": "second high-risk action", "agent_id": 3})
    m._local_executor = local

    state = {
        "task_plan": [{"agent_type": "remediation", "task": "block ip",
                       "dispatch_source": "user_explicit"}],
        "user_id": 1,
        "request_id": "req-reentry",
        "pre_approved": True,
        "approval_status": "approved",
        "approval_round": 0,
        "approval_granted_round": 0,
        "approval_record_id": 42,
    }

    with patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted", new=AsyncMock(return_value=False)):
        state = await m._sub_agent_executor_node(state)

    assert state["pre_approved"] is False
    assert state["approval_round"] == 1
    assert state.get("approval_record_id") is None

    state = await m._validation_node(state)
    assert state["approval_required"] is True
    assert m._validation_decision(state) == "rejected"   # their edge label


@pytest.mark.asyncio
async def test_second_gate_in_one_run_opens_its_own_approval():
    cp = MemorySaver()
    m = _agent(cp)
    m._parse_intent_node = _gated_plan()
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "needs_approval", "output": None,
        "error": "second high-risk action", "agent_id": 3})
    m._local_executor = local

    store = {}
    create, get = _store_backed_approval_service(store)
    thread = f"thread-{uuid.uuid4()}"

    with patch("app.services.approval_service.ApprovalService.create_request", new=create), \
         patch("app.services.approval_service.ApprovalService.get_by_request_id", new=get), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted", new=AsyncMock(return_value=False)):

        first = await m.run(user_input="block the ip", user_id=1,
                            request_id=str(uuid.uuid4()), thread_id=thread)
        assert first.get("interrupted") is True

        second = await m.resume(thread, decision="approved", user_id=1)

    assert second.get("interrupted") is True, (
        "a second gated action must pause for a human, not ride the first approval")
    assert create.await_count == 2
    assert len(store) == 2
