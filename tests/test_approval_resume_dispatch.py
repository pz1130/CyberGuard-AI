"""Only graph-suspended approvals get a resume task.

`internal_agent._request_approval` also writes approval rows (action_type
"tool.execute"). Those have no checkpointed graph thread behind them, so
dispatching a resume for one asks `MasterAgent.resume` to continue a thread
that was never suspended — a failing Celery task plus two retries, once per
decision.
"""
from types import SimpleNamespace

from app.routers.approval import graph_resume_target


def _record(action_type, payload):
    return SimpleNamespace(action_type=action_type, payload=payload,
                           request_id="req-1", user_id=3, risk_level="high")


def test_graph_approval_resumes_on_its_checkpointed_thread():
    target = graph_resume_target(_record("agent_execution", {
        "thread_id": "thread-9", "execution_id": "exec-9",
        "conversation_id": 4, "user_input": "block it",
    }))
    assert target is not None
    assert target["thread_id"] == "thread-9"
    assert target["execution_id"] == "exec-9"
    assert target["conversation_id"] == 4


def test_tool_approval_from_the_internal_agent_is_not_resumed():
    assert graph_resume_target(
        _record("tool.execute", {"tool": "block_ip", "args": {}})) is None


def test_approval_without_a_thread_is_not_resumed():
    """A graph approval predating the thread_id payload cannot be resumed."""
    assert graph_resume_target(_record("agent_execution", {"user_input": "x"})) is None


def test_missing_payload_is_not_resumed():
    assert graph_resume_target(_record("agent_execution", None)) is None


async def test_expired_decision_returns_conflict_without_resuming_graph():
    import pytest
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import HTTPException
    from app.routers.approval import decide_approval
    from app.schemas.approval import ApprovalDecision
    from app.services.approval_service import ApprovalService, ApprovalExpiredError
    record = _record('agent_execution', {'thread_id': 'thread-9'})
    record.status = 'pending'
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute.return_value = result
    with patch.object(ApprovalService, 'decide', AsyncMock(side_effect=ApprovalExpiredError('expired'))), \
         patch('app.workers.tasks.resume_master_agent_task.delay') as dispatch:
        with pytest.raises(HTTPException) as error:
            await decide_approval(1, ApprovalDecision(decision='approved'),
                                  SimpleNamespace(user_id=1), session)
        assert error.value.status_code == 409
        dispatch.assert_not_called()


async def test_self_decision_returns_forbidden_without_resuming_graph():
    import pytest
    from unittest.mock import AsyncMock, MagicMock, patch
    from fastapi import HTTPException
    from app.routers.approval import decide_approval
    from app.schemas.approval import ApprovalDecision
    from app.services.approval_service import ApprovalService, SelfApprovalError

    record = _record("agent_execution", {"thread_id": "thread-9"})
    record.status = "pending"
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute.return_value = result

    with patch.object(
        ApprovalService,
        "decide",
        AsyncMock(side_effect=SelfApprovalError("requester cannot decide own request")),
    ), patch("app.workers.tasks.resume_master_agent_task.delay") as dispatch, patch(
        "app.core.audit.record_action", AsyncMock()
    ) as audit:
        with pytest.raises(HTTPException) as error:
            await decide_approval(
                1,
                ApprovalDecision(decision="approved"),
                SimpleNamespace(user_id=3),
                session,
            )

    assert error.value.status_code == 403
    dispatch.assert_not_called()
    audit.assert_awaited_once()
