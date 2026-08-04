"""P1: provider / ui.prefs / mcp.config RPC — no secrets in responses."""
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
    monkeypatch.delenv("CYBERGUARD_LLM_MODE", raising=False)
    monkeypatch.delenv("CYBERGUARD_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CYBERGUARD_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("CYBERGUARD_LLM_MODEL", raising=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _rpc(method: str, params: dict | None = None) -> dict:
    out = StringIO()
    server = SidecarServer(StringIO(), out)
    await server.handle(
        {"id": "t1", "method": method, "params": params or {}}
    )
    lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
    assert lines, "no response"
    return json.loads(lines[-1])


def _result(msg: dict) -> dict:
    assert "result" in msg, msg
    return msg["result"]


@pytest.mark.asyncio
async def test_provider_get_never_returns_api_key(data_env: Path):
    path = data_env / "provider.json"
    path.write_text(
        json.dumps(
            {
                "mode": "live",
                "base_url": "https://example.invalid/v1",
                "model": "gpt-test",
                "api_key": "sk-should-never-leak",
                "temperature": 0.2,
            }
        ),
        encoding="utf-8",
    )
    res = _result(await _rpc("provider.get"))
    blob = json.dumps(res)
    assert "sk-should-never-leak" not in blob
    assert "api_key" not in res
    assert res["has_api_key"] is True
    assert res["mode"] == "live"
    assert res["model"] == "gpt-test"
    assert res["base_url"] == "https://example.invalid/v1"


@pytest.mark.asyncio
async def test_provider_set_moves_key_to_secrets(data_env: Path):
    res = _result(
        await _rpc(
            "provider.set",
            {
                "mode": "live",
                "base_url": "https://api.example.com/v1",
                "model": "gpt-4o-mini",
                "temperature": 0.4,
                "api_key": "sk-new-secret-key",
            },
        )
    )
    assert res["ok"] is True
    assert res["has_api_key"] is True
    path = data_env / "provider.json"
    file_data = json.loads(path.read_text(encoding="utf-8"))
    assert file_data.get("api_key") in (None, "", False)
    assert "sk-new-secret-key" not in path.read_text(encoding="utf-8")
    assert file_data["mode"] == "live"
    assert file_data["model"] == "gpt-4o-mini"

    from apps.desktop.sidecar.secrets_store import get_provider_api_key

    assert get_provider_api_key() == "sk-new-secret-key"

    got = _result(await _rpc("provider.get"))
    assert got["has_api_key"] is True
    assert "sk-new-secret-key" not in json.dumps(got)


@pytest.mark.asyncio
async def test_provider_test_mock_ok(data_env: Path):
    await _rpc("provider.set", {"mode": "mock", "model": "mock"})
    res = _result(await _rpc("provider.test"))
    assert res["ok"] is True
    assert res.get("mode") == "mock"


@pytest.mark.asyncio
async def test_ui_prefs_roundtrip(data_env: Path):
    res = _result(await _rpc("ui.prefs.get"))
    assert isinstance(res, dict)
    set_res = _result(
        await _rpc("ui.prefs.set", {"theme": "light", "font_size": "medium"})
    )
    assert set_res["ok"] is True
    assert set_res["prefs"]["theme"] == "light"
    assert set_res["prefs"]["font_size"] == "medium"
    got = _result(await _rpc("ui.prefs.get"))
    assert got["theme"] == "light"
    assert got["font_size"] == "medium"


@pytest.mark.asyncio
async def test_mcp_config_list_omits_secrets(data_env: Path):
    path = data_env / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "id": "siem",
                        "command": "/usr/bin/true",
                        "args": ["--demo"],
                        "env": {"TOKEN": "super-secret-token"},
                        "enabled": True,
                        "readonly": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    from apps.desktop.sidecar.secrets_store import set_mcp_secret

    set_mcp_secret("siem", "keychain-secret-value")

    res = _result(await _rpc("mcp.config.list"))
    servers = res["servers"]
    assert len(servers) == 1
    s = servers[0]
    assert s["id"] == "siem"
    assert s["command"] == "/usr/bin/true"
    assert s.get("has_secret") is True
    blob = json.dumps(res)
    assert "super-secret-token" not in blob
    assert "keychain-secret-value" not in blob
    # env values redacted
    env = s.get("env") or {}
    assert env.get("TOKEN") in ("***", "[redacted]", True) or (
        isinstance(env.get("TOKEN"), str) and env["TOKEN"] != "super-secret-token"
    )


@pytest.mark.asyncio
async def test_mcp_config_upsert_and_delete(data_env: Path):
    res = _result(
        await _rpc(
            "mcp.config.upsert",
            {
                "id": "fs",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "readonly": True,
                "enabled": True,
                "description": "files",
                "secret": "mcp-slot-secret",
            },
        )
    )
    assert res["ok"] is True
    path = data_env / "mcp_servers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["servers"][0]["id"] == "fs"
    assert "secret" not in data["servers"][0]
    assert "mcp-slot-secret" not in path.read_text(encoding="utf-8")

    from apps.desktop.sidecar.secrets_store import get_mcp_secret

    assert get_mcp_secret("fs") == "mcp-slot-secret"

    listed = _result(await _rpc("mcp.config.list"))
    assert listed["servers"][0]["has_secret"] is True

    del_res = _result(await _rpc("mcp.config.delete", {"id": "fs"}))
    assert del_res["ok"] is True
    data2 = json.loads(path.read_text(encoding="utf-8"))
    assert data2.get("servers") == []
