"""M1.5: real STDIO MCP client + agent tool routing."""
import json
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "echo_mcp_server.py"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    import importlib
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.mcp_config as mcp_config
    import apps.desktop.sidecar.mcp_stdio as mcp_stdio
    import apps.desktop.sidecar.mcp_manager as mcp_manager

    importlib.reload(paths)
    importlib.reload(mcp_config)
    importlib.reload(mcp_stdio)
    importlib.reload(mcp_manager)
    return root


@pytest.fixture()
def echo_server_cfg(data_dir):
    from apps.desktop.sidecar.mcp_stdio import McpServerConfig
    from apps.desktop.sidecar.paths import data_root

    cfg = {
        "servers": [
            {
                "id": "echo",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "readonly": True,
                "enabled": True,
                "timeout_seconds": 10,
                "description": "test echo MCP",
            }
        ]
    }
    (data_root() / "mcp_servers.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )
    return McpServerConfig.from_dict(cfg["servers"][0])


@pytest.mark.asyncio
async def test_stdio_list_and_call(data_dir, echo_server_cfg):
    from apps.desktop.sidecar.mcp_stdio import STDIO_CLIENT

    tools = await STDIO_CLIENT.list_tools(echo_server_cfg)
    names = {t["name"] for t in tools}
    assert "echo" in names and "list_alerts" in names

    result = await STDIO_CLIENT.call_tool(
        echo_server_cfg, "echo", {"message": "hello"}
    )
    text = result["content"][0]["text"]
    assert "hello" in text

    alerts = await STDIO_CLIENT.call_tool(echo_server_cfg, "list_alerts", {"limit": 2})
    body = alerts["content"][0]["text"]
    assert "A-1001" in body
    assert "A-1003" not in body  # limit 2

    await STDIO_CLIENT.stop(echo_server_cfg.id)


@pytest.mark.asyncio
async def test_discover_tools_for_agent_prefixes(data_dir, echo_server_cfg):
    from apps.desktop.sidecar.mcp_manager import MCP

    tools, routing = await MCP.discover_tools_for_agent(tier="readonly")
    names = [t["function"]["name"] for t in tools]
    assert "mcp__echo__list_alerts" in names
    assert "mcp__echo__echo" in names
    assert all(n.startswith("mcp__") for n in names)

    out = await MCP.call_routed(
        routing, "mcp__echo__list_alerts", {"limit": 1}
    )
    assert "A-1001" in out["content"][0]["text"]
    await MCP.stop_all_async()


@pytest.mark.asyncio
async def test_readonly_hides_non_readonly_servers(data_dir):
    from apps.desktop.sidecar.paths import data_root
    from apps.desktop.sidecar.mcp_manager import MCP

    cfg = {
        "servers": [
            {
                "id": "safe",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "readonly": True,
                "enabled": True,
            },
            {
                "id": "danger",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "readonly": False,
                "enabled": True,
            },
        ]
    }
    (data_root() / "mcp_servers.json").write_text(json.dumps(cfg), encoding="utf-8")

    tools_ro, _ = await MCP.discover_tools_for_agent(tier="readonly")
    names_ro = [t["function"]["name"] for t in tools_ro]
    assert any(n.startswith("mcp__safe__") for n in names_ro)
    assert not any(n.startswith("mcp__danger__") for n in names_ro)

    tools_full, _ = await MCP.discover_tools_for_agent(tier="full")
    names_full = [t["function"]["name"] for t in tools_full]
    assert any(n.startswith("mcp__danger__") for n in names_full)
    await MCP.stop_all_async()


@pytest.mark.asyncio
async def test_agent_run_uses_mcp_tool(data_dir, echo_server_cfg):
    from apps.desktop.sidecar.mock_agent import MockAgentHost

    host = MockAgentHost()
    events = []
    async for ev in host.run(task="list sample alerts", tier="readonly"):
        events.append(ev)

    started = next(e for e in events if e["type"] == "run_started")
    assert "mcp__echo__list_alerts" in started.get("mcp_tools", []) or any(
        n.startswith("mcp__echo__") for n in started.get("mcp_tools", [])
    )
    # mock LLM should call first MCP tool
    assert any(e.get("type") == "tool_call_start" for e in events)
    ends = [e for e in events if e.get("type") == "tool_call_end"]
    assert ends
    # result should carry alert content from fixture
    assert any(
        "A-1001" in str(e.get("result_preview") or "")
        or "message" in str(e.get("result_preview") or "").lower()
        or e.get("error") is False
        for e in ends
    )
    from apps.desktop.sidecar.mcp_manager import MCP

    await MCP.stop_all_async()
