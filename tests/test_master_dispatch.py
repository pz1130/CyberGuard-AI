"""Regression tests for MasterAgent._sub_agent_executor_node result collection.

`asyncio.gather(..., return_exceptions=True)` is used so one failing sub-agent
cannot sink the whole fan-out. The exception branch used to store the failure
under `agent_type` without binding `key`, so the audit/approval reads right
below it either raised NameError (first task failing) or silently attributed
the failure to the previously-processed agent.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.master import MasterAgent


def _master(execute_side_effect):
    m = MasterAgent.__new__(MasterAgent)
    m.executor = AsyncMock()
    m.executor.execute = AsyncMock(side_effect=execute_side_effect)
    return m


def _patches(audit_recorder):
    return (
        patch("app.agents.master.log_audit", audit_recorder),
        patch("app.core.audit.record_action", AsyncMock()),
        patch("app.services.kill_switch.is_halted", AsyncMock(return_value=False)),
    )


async def _run_node(master, task_plan, audit_recorder):
    state = {"task_plan": task_plan, "user_id": 1, "request_id": "req-1"}
    p1, p2, p3 = _patches(audit_recorder)
    with p1, p2, p3:
        return await master._sub_agent_executor_node(state)


@pytest.mark.asyncio
async def test_first_task_raising_does_not_crash_the_node():
    """The first sub-agent blowing up must not take the whole node with it."""
    audit = AsyncMock()
    master = _master(RuntimeError("boom"))

    state = await _run_node(
        master, [{"agent_id": 1, "agent_type": "vuln_scanner", "task": "scan"}], audit)

    results = state["sub_results"]
    assert list(results) == ["vuln_scanner"]
    assert results["vuln_scanner"]["status"] == "failed"
    assert "boom" in results["vuln_scanner"]["error"]


@pytest.mark.asyncio
async def test_failure_is_audited_against_its_own_agent_not_the_previous_one():
    """A later failure must not be attributed to the preceding task's key."""
    audit = AsyncMock()
    master = _master([
        {"status": "completed", "output": "ok", "agent_id": 1},
        RuntimeError("second failed"),
    ])

    state = await _run_node(master, [
        {"agent_id": 1, "agent_type": "threat_intel", "task": "a"},
        {"agent_id": 2, "agent_type": "log_anomaly", "task": "b"},
    ], audit)

    results = state["sub_results"]
    assert results["1"]["status"] == "completed"
    assert results["log_anomaly"]["status"] == "failed"

    # Two audit rows, and the failing one carries the failure — not a copy of
    # the successful agent's result.
    assert audit.await_count == 2
    outputs = [call.kwargs["output_data"] for call in audit.await_args_list]
    assert outputs[0]["status"] == "completed"
    assert outputs[1]["status"] == "failed"


@pytest.mark.asyncio
async def test_needs_approval_from_a_later_task_sets_the_flag():
    """approval_required is read off results[key]; a mis-bound key would look
    at the wrong result and miss the gate."""
    audit = AsyncMock()
    master = _master([
        RuntimeError("first failed"),
        {"status": "needs_approval", "output": None, "agent_id": 2},
    ])

    state = await _run_node(master, [
        {"agent_id": 1, "agent_type": "threat_intel", "task": "a"},
        {"agent_id": 2, "agent_type": "remediation", "task": "b"},
    ], audit)

    assert state["approval_required"] is True
