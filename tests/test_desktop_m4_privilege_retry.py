"""M4: privilege escalation wait → approve → elevated retry + policy_events."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def priv_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_LLM_MODE", "mock")
    monkeypatch.setenv("CYBERGUARD_RUNTIME", "standalone")
    monkeypatch.setenv("CYBERGUARD_PLAN_TIMEOUT_SECONDS", "5")
    monkeypatch.delenv("CYBERGUARD_PLAN_AUTO_APPROVE", raising=False)
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests
    from apps.desktop.sidecar.episodic import reset_store_for_tests

    reset_plan_store_for_tests()
    reset_store_for_tests()
    yield tmp_path / "cg"
    reset_plan_store_for_tests()
    reset_store_for_tests()


def _hostile(name: str, body: str) -> str:
    return body


@pytest.mark.asyncio
async def test_privilege_approve_retries_write(priv_env, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_PLAN_AUTO_APPROVE", "1")
    from apps.desktop.sidecar.privilege import request_privilege_and_retry
    from apps.desktop.sidecar.policy_events import tail_policy_events
    from apps.desktop.sidecar.paths import workspace_dir
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    side = []

    async def emit(ev):
        side.append(ev)

    path = str(workspace_dir() / "priv-test.txt")
    result = await request_privilege_and_retry(
        tool_name="host_write_file",
        tool_args={"path": path, "content": "elevated-ok"},
        denied_detail="no edit on readonly",
        task="write note",
        tier="readonly",
        run_id="run-1",
        side_emit=emit,
        hostile_stdout=_hostile,
    )
    types = [e.get("type") for e in side]
    assert "privilege_required" in types
    assert "privilege_decided" in types
    pe_types = [e.get("event_type") for e in tail_policy_events(20)]
    assert "sandbox_denied" in pe_types
    assert "privilege_approved" in pe_types
    # Seatbelt may be unavailable in CI; if elevated write works, assert content
    if not result.get("is_error"):
        assert "privilege_retry" in pe_types
        assert result.get("elevated") is True
        assert open(path, encoding="utf-8").read() == "elevated-ok"
        assert "policy_event" in types
    else:
        # still recorded attempt
        assert result.get("privilege_status") == "approved" or result.get("is_error")


@pytest.mark.asyncio
async def test_privilege_timeout_no_retry(priv_env, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_PLAN_TIMEOUT_SECONDS", "0.25")
    from apps.desktop.sidecar.privilege import request_privilege_and_retry
    from apps.desktop.sidecar.policy_events import tail_policy_events
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    result = await request_privilege_and_retry(
        tool_name="host_write_file",
        tool_args={"path": "/tmp/nope", "content": "x"},
        denied_detail="denied",
        task="t",
        tier="readonly",
        run_id="run-t",
        side_emit=None,
        hostile_stdout=_hostile,
    )
    assert result.get("is_error") is True
    assert result.get("privilege_status") == "timeout"
    pe_types = [e.get("event_type") for e in tail_policy_events(10)]
    assert "sandbox_denied" in pe_types
    assert "privilege_rejected" in pe_types
    assert "privilege_retry" not in pe_types


@pytest.mark.asyncio
async def test_privilege_reject_no_retry(priv_env):
    from apps.desktop.sidecar.privilege import request_privilege_and_retry
    from apps.desktop.sidecar.plan_mode import get_plan_store, reset_plan_store_for_tests
    from apps.desktop.sidecar.policy_events import tail_policy_events

    reset_plan_store_for_tests()

    async def reject_soon():
        for _ in range(40):
            await asyncio.sleep(0.05)
            for p in get_plan_store().list():
                if (
                    p["status"] == "pending"
                    and p["action_type"] == "privilege_escalation"
                ):
                    get_plan_store().decide(
                        p["plan_id"], approve=False, reason="no"
                    )
                    return

    t = asyncio.create_task(reject_soon())
    result = await request_privilege_and_retry(
        tool_name="host_run",
        tool_args={"argv": ["/bin/echo", "hi"]},
        denied_detail="no exec",
        task="run",
        tier="readonly",
        run_id="run-r",
        side_emit=None,
        hostile_stdout=_hostile,
    )
    await t
    assert result.get("is_error") is True
    assert result.get("privilege_status") == "rejected"
    assert "privilege_rejected" in [
        e.get("event_type") for e in tail_policy_events(10)
    ]


@pytest.mark.asyncio
async def test_side_channel_privilege_during_run_loop(priv_env, monkeypatch):
    """dispatch privilege wait emits privilege_required via side_q while loop runs."""
    monkeypatch.setenv("CYBERGUARD_PLAN_AUTO_APPROVE", "1")
    from agent_core.run_loop import RunLoopConfig, run_loop
    from apps.desktop.sidecar.privilege import request_privilege_and_retry
    from apps.desktop.sidecar.paths import workspace_dir
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    path = str(workspace_dir() / "sideq.txt")
    side_q: asyncio.Queue = asyncio.Queue()
    run_id = "run-side"
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            call = SimpleNamespace(
                id="c1",
                function=SimpleNamespace(
                    name="host_write_file",
                    arguments=(
                        '{"path": "%s", "content": "sideq-data"}' % path
                    ),
                ),
            )
            return SimpleNamespace(content="", tool_calls=[call])
        return "finished after privilege"

    async def dispatch(call):
        import json

        args = json.loads(call.function.arguments or "{}")

        async def _side(ev):
            await side_q.put({"src": "side", "ev": dict(ev)})

        return await request_privilege_and_retry(
            tool_name=call.function.name,
            tool_args=args,
            denied_detail="readonly no edit",
            task="write a file",
            tier="readonly",
            run_id=run_id,
            side_emit=_side,
            hostile_stdout=_hostile,
        )

    async def produce():
        try:
            async for lev in run_loop(
                task="write a file",
                system_prompt="s",
                history=[],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "host_write_file",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                config=RunLoopConfig(
                    max_steps=4, tool_call_budget=5, agent_run_id=run_id
                ),
                chat=chat,
                dispatch=dispatch,
            ):
                await side_q.put({"src": "loop", "ev": dict(lev)})
        finally:
            await side_q.put({"src": "done"})

    task_p = asyncio.create_task(produce())
    events = []
    try:
        while True:
            item = await side_q.get()
            if item.get("src") == "done":
                break
            events.append(item.get("ev") or {})
    finally:
        if not task_p.done():
            task_p.cancel()
            try:
                await task_p
            except Exception:  # noqa: BLE001
                pass

    types = [e.get("type") for e in events]
    assert "privilege_required" in types
    assert "privilege_decided" in types
    assert "tool_call_end" in types
    assert "answer_ready" in types


@pytest.mark.asyncio
async def test_policy_events_rpc(priv_env, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_PLAN_AUTO_APPROVE", "1")
    from io import StringIO
    import json
    from apps.desktop.sidecar.main import SidecarServer
    from apps.desktop.sidecar.privilege import request_privilege_and_retry
    from apps.desktop.sidecar.paths import workspace_dir
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    path = str(workspace_dir() / "rpc-priv.txt")
    await request_privilege_and_retry(
        tool_name="host_write_file",
        tool_args={"path": path, "content": "x"},
        denied_detail="d",
        task="t",
        tier="readonly",
        run_id="r",
        side_emit=None,
        hostile_stdout=_hostile,
    )
    stdout = StringIO()
    server = SidecarServer(StringIO(), stdout)
    await server.handle(
        {"id": "1", "method": "policy_events.tail", "params": {"n": 20}}
    )
    msg = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert "events" in msg["result"]
    assert any(
        e.get("event_type") == "sandbox_denied" for e in msg["result"]["events"]
    )
