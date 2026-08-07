"""The human-approval loop actually closes.

Two failures this file pins down:

1. A human approves, the graph re-dispatches — and the sub-agent refuses again
   because nothing downstream ever read ``pre_approved``. The approved action
   never ran; the run just summarised itself.
2. ``approval_status`` stayed ``"approved"`` for the life of the thread, so the
   *next* gated action in the same run was waved through without a human ever
   seeing it.
"""
import pytest
from unittest.mock import AsyncMock, patch

from langgraph.checkpoint.memory import MemorySaver

from app.agents.master import MasterAgent
from app.services.agent_executor import AgentExecutor
from app.services.internal_agent import InternalAgentRunner


_EXTERNAL_HIGH = {
    "id": 7,
    "agent_name": "remediation-bot",
    "kind": "external",
    "backend_type": "custom",
    "permission_level": "high",
    "endpoint_url": None,          # keeps the test off the network
    "env_vars_encrypted": None,
}


@pytest.mark.asyncio
async def test_high_permission_agent_is_gated_without_pre_approval():
    ex = AgentExecutor()
    with patch.object(ex, "_load_config_dict",
                      new=AsyncMock(return_value=dict(_EXTERNAL_HIGH))):
        result = await ex.execute(agent_id=7, task="block 10.0.0.1", user_id=1)
    assert result["status"] == "needs_approval"


@pytest.mark.asyncio
async def test_pre_approved_context_lets_the_approved_action_run():
    """After a human approves, the re-dispatch must get past the gate.

    Without this the graph re-executes, hits the same blanket refusal, and the
    approved action is never performed.
    """
    ex = AgentExecutor()
    with patch.object(ex, "_load_config_dict",
                      new=AsyncMock(return_value=dict(_EXTERNAL_HIGH))):
        result = await ex.execute(agent_id=7, task="block 10.0.0.1", user_id=1,
                                  context={"pre_approved": True})
    # It gets as far as the transport (which has no endpoint here) instead of
    # being refused by the permission gate.
    assert result["status"] != "needs_approval"


def _internal_runner(**kwargs):
    cfg = {"id": 1, "agent_name": "internal-ir", "system_prompt": "",
           "knowledge_base_id": 9, "associated_skills": [],
           "metadata_json": {"enable_search": True},
           "permission_level": "medium", "autonomy_tier": "L2",
           "allowed_categories": ["observe"], "is_poc": True}
    r = InternalAgentRunner(cfg, **kwargs)
    r._mcp_by_name = {}
    r._user_id = 1
    return r


@pytest.mark.asyncio
async def test_internal_runner_pre_approval_is_spent_on_the_first_gate(monkeypatch):
    """A human approved one action, not unlimited gated actions for the run."""
    from app.services.gatekeeper import Decision

    monkeypatch.setattr("app.core.audit.record_action", AsyncMock())
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=False))
    monkeypatch.setattr(
        "app.services.gatekeeper.gatekeeper_check",
        lambda meta, gov, confidence=None: type("V", (), {
            "decision": Decision.NEEDS_APPROVAL, "reason": "high risk",
            "category": "remediate", "risk_tier": "high"})(),
    )
    raised = AsyncMock()
    monkeypatch.setattr("app.services.approval_service.ApprovalService.create_request",
                        raised)

    r = _internal_runner(pre_approved=True)
    meta = {"action_category": "remediate", "risk_tier": "high"}

    first = await r._govern("block_ip", {"ip": "10.0.0.1"}, meta)
    assert first is None, "the approved action must be allowed to run"
    raised.assert_not_awaited()

    second = await r._govern("wipe_host", {"host": "srv1"}, meta)
    assert second is not None and second.status == "needs_approval"
    assert second.terminate is True


@pytest.mark.asyncio
async def test_pre_approved_is_consumed_and_a_new_gate_pauses_again():
    """One approval must authorise one dispatch, not the whole thread."""
    m = MasterAgent(llm_router=None, checkpointer=MemorySaver())
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "needs_approval", "output": None,
        "error": "second high-risk action", "agent_id": 3,
    })
    m._local_executor = local

    state = {
        "task_plan": [{"agent_type": "remediation", "task": "block ip"}],
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
         patch("app.services.kill_switch.is_halted",
               new=AsyncMock(return_value=False)):
        state = await m._sub_agent_executor_node(state)

    assert state["pre_approved"] is False
    assert state["approval_required"] is True
    # The decision stays on the record, but it no longer covers the new gate:
    # the round moved on and the spent approval record is released.
    assert state["approval_status"] == "approved"
    assert state["approval_round"] == 1
    assert state.get("approval_record_id") is None

    state = await m._validation_node(state)
    assert m._validation_decision(state) == "needs_approval"


def test_per_round_request_ids_fit_the_column_and_are_deterministic():
    """approval_requests.request_id is String(36) — a suffixed uuid overflows."""
    from app.agents.master import approval_request_id

    run_id = "5f8c1b3e-9a2d-4f61-8b7c-0d1e2f3a4b5c"   # 36 chars
    assert approval_request_id(run_id, 0) == run_id
    for rnd in (1, 2, 17):
        rid = approval_request_id(run_id, rnd)
        assert len(rid) <= 36, rid
        assert rid != run_id
        # Stable across the node re-running on resume.
        assert rid == approval_request_id(run_id, rnd)
    assert approval_request_id(run_id, 1) != approval_request_id(run_id, 2)


@pytest.mark.asyncio
async def test_resume_does_not_open_a_second_approval_record():
    """``interrupt()`` discards the node's own state writes.

    So the "create the request only once" guard cannot be a state flag — on
    resume the node re-runs with ``approval_record_id`` unset and opens a
    duplicate, leaving a dangling pending approval behind every approved run.
    Idempotency has to come from the request_id.
    """
    cp = MemorySaver()
    store = {}

    async def fake_parse(state):
        state["task_plan"] = [{
            "agent_type": "remediation", "task": "block ip",
            "requires_approval": True,
        }]
        state["intent"] = "task_execution"
        return state

    async def fake_create(*, request_id, **kwargs):
        record = type("R", (), {"id": len(store) + 1, "request_id": request_id})()
        store[request_id] = record
        return record

    async def fake_get(request_id):
        return store.get(request_id)

    m = MasterAgent(llm_router=None, checkpointer=cp)
    m._parse_intent_node = fake_parse  # type: ignore
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "completed", "output": "blocked", "agent_id": 1,
    })
    m._local_executor = local

    create = AsyncMock(side_effect=fake_create)
    with patch("app.services.approval_service.ApprovalService.create_request",
               new=create), \
         patch("app.services.approval_service.ApprovalService.get_by_request_id",
               new=AsyncMock(side_effect=fake_get)), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted",
               new=AsyncMock(return_value=False)):

        await m.run(user_input="block the ip", user_id=1,
                    request_id="req-once", thread_id="thread-once")
        await m.resume("thread-once", decision="approved", user_id=1)

    assert create.await_count == 1, (
        f"resume re-opened the approval request: {list(store)}")


@pytest.mark.asyncio
async def test_second_gate_in_one_run_raises_a_second_approval_request():
    """End to end: approve once, hit another gate, suspend again."""
    cp = MemorySaver()

    async def fake_parse(state):
        state["task_plan"] = [{
            "agent_type": "remediation", "task": "block ip",
            "requires_approval": True,
        }]
        state["intent"] = "task_execution"
        return state

    m = MasterAgent(llm_router=None, checkpointer=cp)
    m._parse_intent_node = fake_parse  # type: ignore
    local = AsyncMock()
    # The re-dispatch hits a *different* gated action and is refused again.
    local.execute = AsyncMock(return_value={
        "status": "needs_approval", "output": None,
        "error": "second high-risk action", "agent_id": 3,
    })
    m._local_executor = local

    store = {}

    async def fake_create(*, request_id, **kwargs):
        record = type("R", (), {"id": len(store) + 1, "request_id": request_id})()
        store[request_id] = record
        return record

    create = AsyncMock(side_effect=fake_create)

    with patch("app.services.approval_service.ApprovalService.create_request",
               new=create), \
         patch("app.services.approval_service.ApprovalService.get_by_request_id",
               new=AsyncMock(side_effect=lambda rid: store.get(rid))), \
         patch("app.config.settings.AUTO_APPROVE", False), \
         patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted",
               new=AsyncMock(return_value=False)):

        first = await m.run(user_input="block the ip", user_id=1,
                            request_id="req-reentry-2",
                            thread_id="thread-reentry-2")
        assert first.get("interrupted") is True

        second = await m.resume("thread-reentry-2", decision="approved",
                                comment="ok", user_id=1)

    assert second.get("interrupted") is True, (
        "a second gated action must pause for a human, not be waved through "
        "on the first approval"
    )
    # Two distinct approvals — the second gate does not reuse the spent one.
    assert create.await_count == 2, list(store)
    assert len(store) == 2
