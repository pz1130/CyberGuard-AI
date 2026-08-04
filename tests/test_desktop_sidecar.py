"""M1 desktop sidecar: capabilities tiers, headless JSONL, abort."""
import asyncio
import json
from io import StringIO

import pytest

from agent_core.run_loop import RunLoopConfig, run_loop
from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.mock_agent import MockAgentHost
from apps.desktop.sidecar.main import SidecarServer


def test_readonly_has_no_exec_operations():
    caps = capabilities_for_tier("readonly")
    assert caps.operations.exec is None
    assert caps.operations.edit is None
    assert caps.operations.read is not None
    assert caps.has_local_exec() is False


def test_full_has_mock_exec():
    caps = capabilities_for_tier("full")
    assert caps.operations.exec is not None
    assert caps.has_local_exec() is True


@pytest.mark.asyncio
async def test_run_loop_abort_within_steps():
    from types import SimpleNamespace

    abort = asyncio.Event()
    step = {"n": 0}

    async def chat(*, messages, tools=None):
        step["n"] += 1
        if step["n"] == 1:
            call = SimpleNamespace(
                id="c1",
                function=SimpleNamespace(name="t", arguments="{}"),
            )
            return SimpleNamespace(content="", tool_calls=[call])
        # During second model call, abort is already set from dispatch
        await asyncio.sleep(0.02)
        return "should-not-finish"

    async def dispatch(call):
        abort.set()
        await asyncio.sleep(0.01)
        return "tool-out"

    events = []
    async for ev in run_loop(
        task="t",
        system_prompt="s",
        history=[],
        tools=[{"type": "function"}],
        config=RunLoopConfig(max_steps=10, tool_call_budget=5, agent_name="t"),
        chat=chat,
        dispatch=dispatch,
        abort_event=abort,
    ):
        events.append(ev)

    assert any(e.get("status") == "aborted" for e in events)
    assert not any(e.get("type") == "answer_ready" for e in events)


@pytest.mark.asyncio
async def test_mock_agent_readonly_no_local_exec(tmp_path, monkeypatch):
    """Readonly has no ExecOperations; without MCP config there are no tools."""
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    import importlib
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.mcp_config as mcp_config
    importlib.reload(paths)
    importlib.reload(mcp_config)

    host = MockAgentHost()
    types = []
    started = None
    async for ev in host.run(task="hello", tier="readonly"):
        types.append(ev["type"])
        if ev["type"] == "run_started":
            started = ev
    assert started and started["capabilities"]["has_exec"] is False
    assert started.get("mcp_tools") == []
    assert "tool_call_start" not in types
    assert "answer_ready" in types or "error" in types


@pytest.mark.asyncio
async def test_mock_agent_full_may_tool_call(monkeypatch, tmp_path):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_PLAN_AUTO_APPROVE", "1")
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()
    host = MockAgentHost()
    types = []
    async for ev in host.run(task="scan", tier="full"):
        types.append(ev["type"])
    assert "plan_ready" in types or "plan_approved" in types
    assert "tool_call_start" in types
    assert "answer_ready" in types


@pytest.mark.asyncio
async def test_sidecar_ping_jsonl():
    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)
    await server.handle({"id": "1", "method": "ping", "params": {}})
    line = stdout.getvalue().strip().splitlines()[-1]
    msg = json.loads(line)
    assert msg["id"] == "1"
    assert msg["result"]["ok"] is True


@pytest.mark.asyncio
async def test_sidecar_capabilities_readonly():
    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)
    await server.handle(
        {"id": "2", "method": "session.capabilities", "params": {"tier": "readonly"}}
    )
    msg = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert msg["result"]["has_exec"] is False
