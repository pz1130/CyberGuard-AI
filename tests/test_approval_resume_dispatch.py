"""Only graph-suspended approvals get a resume task.

`internal_agent._request_approval` also writes approval rows (action_type
"tool.execute"). Those have no checkpointed thread, so dispatching a resume for
them makes `MasterAgent.resume` fail against a thread_id that was never
suspended — once per decision, plus two Celery retries.
"""
from types import SimpleNamespace

from app.routers.approval import graph_resume_target


def _record(action_type, payload):
    return SimpleNamespace(action_type=action_type, payload=payload,
                           request_id="req-1", user_id=3)


def test_graph_approval_resumes_on_its_checkpointed_thread():
    record = _record("agent_execution", {
        "thread_id": "thread-9", "execution_id": "exec-9",
        "conversation_id": 4, "user_input": "block it",
    })
    target = graph_resume_target(record)
    assert target is not None
    assert target["thread_id"] == "thread-9"
    assert target["execution_id"] == "exec-9"
    assert target["conversation_id"] == 4


def test_tool_approval_from_the_internal_agent_is_not_resumed():
    record = _record("tool.execute", {"tool": "block_ip", "args": {}})
    assert graph_resume_target(record) is None


def test_approval_without_a_thread_is_not_resumed():
    """A graph approval predating the thread_id payload cannot be resumed."""
    record = _record("agent_execution", {"user_input": "x"})
    assert graph_resume_target(record) is None


def test_missing_payload_is_not_resumed():
    assert graph_resume_target(_record("agent_execution", None)) is None
