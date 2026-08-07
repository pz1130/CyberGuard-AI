"""Audit #22: the graph can see inside the internal agent's tool loop.

`master._sub_agent_executor_node` pulls `agent_run_events` into
`state["loop_events"]` keyed on the sub-result's `run_id` — which the runner
never returned, so the whole path was unreachable.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langgraph.checkpoint.memory import MemorySaver

from app.agents.master import MasterAgent
from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner


def _runner():
    cfg = {"id": 1, "agent_name": "loop-agent", "system_prompt": "",
           "associated_skills": [], "metadata_json": {}, "tool_loop_max_steps": 2}
    r = InternalAgentRunner(cfg)
    r._mcp_by_name = {}
    return r


@pytest.mark.asyncio
async def test_execute_reports_the_run_id_it_logged_under(monkeypatch):
    r = _runner()
    monkeypatch.setattr(r, "_append_memory", AsyncMock())
    monkeypatch.setattr(r, "_build_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(r, "_build_system_prompt", AsyncMock(return_value="sys"))
    monkeypatch.setattr(r, "_load_memory", AsyncMock(return_value=[]))
    monkeypatch.setattr(r, "_resolve_mcp_lookup", AsyncMock())

    router = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(
        content="done", tool_calls=None, finish_reason="stop")))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: router)

    logged = {}

    class FakeLog:
        def __init__(self, **kwargs):
            self.run_id = "run-abc"
            logged["run_id"] = self.run_id

        async def append(self, *a, **k):
            return 0

    monkeypatch.setattr("app.services.run_event_log.RunEventLog", FakeLog)

    result = await r.execute(task="scan", conversation_id=None, user_id=1)

    assert result["status"] == "completed"
    assert result["run_id"] == logged["run_id"]


@pytest.mark.asyncio
async def test_executor_node_surfaces_loop_events_for_a_reported_run_id():
    m = MasterAgent(llm_router=None, checkpointer=MemorySaver())
    local = AsyncMock()
    local.execute = AsyncMock(return_value={
        "status": "completed", "output": "ok", "agent_id": 5,
        "run_id": "run-xyz",
    })
    m._local_executor = local
    m._fetch_loop_events = AsyncMock(return_value=[
        {"run_id": "run-xyz", "seq": 0, "event_type": "run_started",
         "payload": {}, "replay": None},
    ])

    from unittest.mock import patch
    with patch("app.core.audit.record_action", new=AsyncMock()), \
         patch("app.agents.master.log_audit", new=AsyncMock()), \
         patch("app.services.kill_switch.is_halted",
               new=AsyncMock(return_value=False)):
        state = await m._sub_agent_executor_node({
            "task_plan": [{"agent_type": "general", "task": "scan"}],
            "user_id": 1,
        })

    m._fetch_loop_events.assert_awaited_once_with("run-xyz")
    assert state["loop_events"][0]["event_type"] == "run_started"
