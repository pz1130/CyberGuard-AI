"""M1.5/M3: real STDIO MCP client + agent tool routing + secret injection."""
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
    import apps.desktop.sidecar.secrets_store as secrets_store

    importlib.reload(paths)
    importlib.reload(secrets_store)
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
    assert "secret_probe" in names

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

    out = await MCP.call_routed(routing, "mcp__echo__list_alerts", {"limit": 1})
    assert "A-1001" in out["content"][0]["text"]
    await MCP.stop_all_async()


@pytest.mark.asyncio
async def test_mcp_secret_injected_from_slot(data_dir, echo_server_cfg, monkeypatch):
    """M3: only this server's Keychain/file slot is injected into child env."""
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    from apps.desktop.sidecar.mcp_stdio import STDIO_CLIENT
    from apps.desktop.sidecar.secrets_store import set_mcp_secret

    set_mcp_secret("echo", "super-secret-token-9999")
    set_mcp_secret("other", "other-server-secret-xxxx")

    # ensure fresh process so env is applied at spawn
    await STDIO_CLIENT.stop(echo_server_cfg.id)
    result = await STDIO_CLIENT.call_tool(echo_server_cfg, "secret_probe", {})
    body = json.loads(result["content"][0]["text"])
    assert body["has_secret"] is True
    assert body["suffix"] == "9999"
    assert body["length"] == len("super-secret-token-9999")
    assert "super-secret-token-9999" not in result["content"][0]["text"]
    # other server's secret must not appear
    assert "xxxx" not in result["content"][0]["text"]

    await STDIO_CLIENT.stop(echo_server_cfg.id)


@pytest.mark.asyncio
async def test_mcp_secret_env_custom_name(data_dir, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    from apps.desktop.sidecar.mcp_stdio import McpServerConfig, STDIO_CLIENT
    from apps.desktop.sidecar.paths import data_root
    from apps.desktop.sidecar.secrets_store import set_mcp_secret

    cfg_data = {
        "servers": [
            {
                "id": "echo",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "readonly": True,
                "enabled": True,
                "timeout_seconds": 10,
                "secret_env": "MY_SIEM_TOKEN",
            }
        ]
    }
    (data_root() / "mcp_servers.json").write_text(
        json.dumps(cfg_data), encoding="utf-8"
    )
    set_mcp_secret("echo", "custom-env-secret-42")
    cfg = McpServerConfig.from_dict(cfg_data["servers"][0])
    await STDIO_CLIENT.stop("echo")
    result = await STDIO_CLIENT.call_tool(
        cfg, "secret_probe", {"env_name": "MY_SIEM_TOKEN"}
    )
    body = json.loads(result["content"][0]["text"])
    assert body["has_secret"] is True
    assert body["suffix"] == "t-42"
    assert body["length"] == len("custom-env-secret-42")
    await STDIO_CLIENT.stop("echo")


def test_configured_servers_reports_has_secret(data_dir, echo_server_cfg, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    from apps.desktop.sidecar.mcp_manager import MCP
    from apps.desktop.sidecar.secrets_store import set_mcp_secret

    rows = MCP.configured_servers()
    echo = next(r for r in rows if r["id"] == "echo")
    assert echo["has_secret"] is False
    set_mcp_secret("echo", "x")
    rows2 = MCP.configured_servers()
    echo2 = next(r for r in rows2 if r["id"] == "echo")
    assert echo2["has_secret"] is True
    assert echo2.get("secret_env")


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
    assert any(e.get("type") == "tool_call_start" for e in events)
    ends = [e for e in events if e.get("type") == "tool_call_end"]
    assert ends
    assert any(
        "A-1001" in str(e.get("result_preview") or "")
        or "message" in str(e.get("result_preview") or "").lower()
        or e.get("error") is False
        for e in ends
    )
    from apps.desktop.sidecar.mcp_manager import MCP

    await MCP.stop_all_async()
