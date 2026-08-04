"""M4: Plan Mode, timeout=reject, self-approval label, SoD no local approve."""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def plan_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_LLM_MODE", "mock")
    monkeypatch.delenv("CYBERGUARD_PLAN_AUTO_APPROVE", raising=False)
    monkeypatch.setenv("CYBERGUARD_PLAN_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("CYBERGUARD_RUNTIME", "standalone")
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests
    from apps.desktop.sidecar.episodic import reset_store_for_tests

    reset_plan_store_for_tests()
    reset_store_for_tests()
    yield
    reset_plan_store_for_tests()
    reset_store_for_tests()


def test_plan_required_for_irreversible_and_risk():
    from apps.desktop.sidecar.plan_mode import plan_required

    assert plan_required(tier="readonly", task="hello", tool_names=["load_skill"]) is False
    # "skill" must not trip keyword "kill"
    assert (
        plan_required(
            tier="readonly",
            task="load_skill for CVE impact assessment procedure",
            tool_names=["load_skill"],
        )
        is False
    )
    assert plan_required(
        tier="readonly", task="hello", tool_names=["host_run", "load_skill"]
    )
    assert plan_required(tier="full", task="anything", tool_names=["load_skill"])
    assert plan_required(
        tier="readonly", task="please scan the dmz", tool_names=["load_skill"]
    )


@pytest.mark.asyncio
async def test_timeout_async(plan_env):
    from apps.desktop.sidecar.plan_mode import STATUS_TIMEOUT, get_plan_store, draft_plan

    store = get_plan_store()
    req = store.create(
        task="t",
        tier="full",
        plan=draft_plan(task="t", tier="full", tool_names=["mock_scan"]),
        timeout_seconds=0.25,
    )
    decided = await store.wait_decision(req.plan_id)
    assert decided.status == STATUS_TIMEOUT
    assert "timeout" in decided.reason


@pytest.mark.asyncio
async def test_approve_with_revised_plan(plan_env):
    from apps.desktop.sidecar.plan_mode import (
        STATUS_APPROVED,
        get_plan_store,
        draft_plan,
    )

    store = get_plan_store()
    req = store.create(
        task="scan x",
        tier="full",
        plan=draft_plan(task="scan x", tier="full", tool_names=["mock_scan"]),
        timeout_seconds=5,
    )

    async def approve_soon():
        await asyncio.sleep(0.05)
        store.decide(
            req.plan_id,
            approve=True,
            revised_plan="Only run mock_scan on lab net 10.0.0.0/24",
        )

    task = asyncio.create_task(approve_soon())
    decided = await store.wait_decision(req.plan_id)
    await task
    assert decided.status == STATUS_APPROVED
    assert "lab net" in (decided.revised_plan or "")
    pub = decided.public_dict()
    assert pub["approval_type"] == "self"
    assert pub["ui_label"] == "自批准"
    assert pub["local_approve_allowed"] is False  # already decided


def test_connected_segregation_no_local_approve(plan_env, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_RUNTIME", "connected")
    from apps.desktop.sidecar.plan_mode import (
        ACTION_PRIVILEGE_ESCALATION,
        get_plan_store,
        draft_plan,
        reset_plan_store_for_tests,
    )

    reset_plan_store_for_tests()
    store = get_plan_store()
    req = store.create(
        task="elevate",
        tier="readonly",
        plan=draft_plan(task="elevate", tier="readonly", tool_names=[]),
        action_type=ACTION_PRIVILEGE_ESCALATION,
        denied_action="host_write_file",
    )
    assert req.approval_type == "segregation"
    assert req.local_approve_allowed() is False
    out = store.decide(req.plan_id, approve=True)
    assert out["ok"] is False
    assert out["error"] == "local_approve_forbidden"


@pytest.mark.asyncio
async def test_agent_waits_for_plan_then_runs(plan_env):
    from apps.desktop.sidecar.mock_agent import MockAgentHost
    from apps.desktop.sidecar.plan_mode import get_plan_store

    host = MockAgentHost()
    events = []

    async def approve_when_ready():
        for _ in range(50):
            await asyncio.sleep(0.05)
            for p in get_plan_store().list():
                if p["status"] == "pending":
                    get_plan_store().decide(p["plan_id"], approve=True)
                    return

    t = asyncio.create_task(approve_when_ready())
    async for ev in host.run(task="scan lab network carefully", tier="full"):
        events.append(ev)
    await t
    types = [e.get("type") for e in events]
    assert "plan_ready" in types
    assert "plan_approved" in types
    assert "plan_rejected" not in types
    assert "answer_ready" in types or "error" in types
    approved = next(e for e in events if e.get("type") == "plan_approved")
    assert approved.get("approval_type") == "self"
    assert approved.get("ui_label") == "自批准"


@pytest.mark.asyncio
async def test_agent_plan_timeout_stops_without_tools(plan_env, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_PLAN_TIMEOUT_SECONDS", "0.3")
    from apps.desktop.sidecar.mock_agent import MockAgentHost
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    host = MockAgentHost()
    events = []
    async for ev in host.run(task="scan production", tier="full"):
        events.append(ev)
    types = [e.get("type") for e in events]
    assert "plan_ready" in types
    assert "plan_rejected" in types
    assert "tool_call_start" not in types
    rej = next(e for e in events if e.get("type") == "plan_rejected")
    assert rej.get("status") == "timeout" or "timeout" in str(rej.get("reason"))


@pytest.mark.asyncio
async def test_rpc_plan_approve_reject(plan_env):
    from io import StringIO
    import json
    from apps.desktop.sidecar.main import SidecarServer
    from apps.desktop.sidecar.plan_mode import get_plan_store, draft_plan

    store = get_plan_store()
    req = store.create(
        task="t",
        tier="full",
        plan=draft_plan(task="t", tier="full", tool_names=["host_run"]),
        timeout_seconds=30,
    )
    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)
    await server.handle(
        {
            "id": "a1",
            "method": "plan.approve",
            "params": {"plan_id": req.plan_id, "revised_plan": "step 1 only"},
        }
    )
    msg = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert msg["result"]["ok"] is True
    assert msg["result"]["plan"]["status"] == "approved"
    assert msg["result"]["plan"]["approval_type"] == "self"

    req2 = store.create(
        task="t2",
        tier="full",
        plan=draft_plan(task="t2", tier="full", tool_names=["host_run"]),
    )
    stdout2 = StringIO()
    server2 = SidecarServer(stdin, stdout2)
    await server2.handle(
        {
            "id": "r1",
            "method": "plan.reject",
            "params": {"plan_id": req2.plan_id, "reason": "too risky"},
        }
    )
    msg2 = json.loads(stdout2.getvalue().strip().splitlines()[-1])
    assert msg2["result"]["ok"] is True
    assert msg2["result"]["plan"]["status"] == "rejected"
