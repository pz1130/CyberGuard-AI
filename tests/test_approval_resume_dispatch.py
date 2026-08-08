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
                           request_id="req-1", user_id=3)


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
