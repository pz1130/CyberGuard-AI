"""File-backed alerts MCP + install RPC."""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from apps.desktop.sidecar.main import SidecarServer


@pytest.fixture
def data_env(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _rpc(method: str, params: dict | None = None) -> dict:
    out = StringIO()
    server = SidecarServer(StringIO(), out)
    await server.handle({"id": "1", "method": method, "params": params or {}})
    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
    return json.loads(lines[-1])


@pytest.mark.asyncio
async def test_install_file_alerts_mcp_sample(data_env: Path):
    msg = await _rpc("mcp.config.install_file_alerts")
    assert "result" in msg, msg
    res = msg["result"]
    assert res["ok"] is True
    assert res["server"]["id"] == "file-alerts"
    assert res["server"]["readonly"] is True
    raw = json.loads((data_env / "mcp_servers.json").read_text(encoding="utf-8"))
    args = raw["servers"][0]["args"]
    assert any("file_alerts_mcp_server.py" in str(a) for a in args)
    assert any("sample_alerts.json" in str(a) for a in args)

    disc = await _rpc("mcp.discover", {"tier": "readonly"})
    names = [t["name"] for t in disc["result"].get("tools") or []]
    assert any("list_alerts" in n for n in names)
    assert any("search_alerts" in n for n in names)
    assert any("get_alert" in n for n in names)


@pytest.mark.asyncio
async def test_file_alerts_tools_call_sample(data_env: Path, tmp_path):
    await _rpc("mcp.config.install_file_alerts")
    # call via mcp.call after discover routing
    disc = await _rpc("mcp.discover", {"tier": "readonly"})
    names = [t["name"] for t in disc["result"].get("tools") or []]
    list_name = next(n for n in names if n.endswith("list_alerts"))
    msg = await _rpc(
        "mcp.call",
        {"name": list_name, "arguments": {"limit": 3, "severity": "high"}, "tier": "readonly"},
    )
    assert "result" in msg, msg
    blob = json.dumps(msg["result"])
    assert "ALT-2026" in blob or "severity" in blob
