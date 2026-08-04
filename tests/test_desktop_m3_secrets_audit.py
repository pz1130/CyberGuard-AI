"""M3: secrets store + local audit hash chain."""
from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from apps.desktop.sidecar import audit_chain
from apps.desktop.sidecar.secrets_store import (
    SERVICE_PROVIDER,
    delete_mcp_secret,
    delete_secret,
    get_mcp_secret,
    get_provider_api_key,
    get_secret,
    has_secret,
    mcp_service,
    public_status,
    set_mcp_secret,
    set_provider_api_key,
    set_secret,
)


@pytest.fixture
def secrets_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    return tmp_path / "cg"


def test_provider_secret_roundtrip(secrets_env):
    assert has_secret(SERVICE_PROVIDER, "default") is False
    set_provider_api_key("sk-test-key-123")
    assert has_secret(SERVICE_PROVIDER, "default") is True
    assert get_provider_api_key() == "sk-test-key-123"
    st = public_status()
    assert st["backend"] == "file"
    assert st["provider_key_present"] is True
    assert delete_secret(SERVICE_PROVIDER, "default") is True
    assert get_provider_api_key() is None


def test_auto_backend_prefers_existing_secrets_file(tmp_path, monkeypatch):
    """Electron auto-backend must not ignore secrets.json written by headless migrate."""
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.delenv("CYBERGUARD_SECRETS_BACKEND", raising=False)
    from apps.desktop.sidecar import secrets_store as ss

    # force re-read with auto
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    set_provider_api_key("sk-from-file")
    monkeypatch.delenv("CYBERGUARD_SECRETS_BACKEND", raising=False)
    # auto should stick to file because secrets.json is non-empty
    assert ss._backend() == "file"
    assert get_provider_api_key() == "sk-from-file"


def test_mcp_slots_are_isolated(secrets_env):
    set_mcp_secret("siem-a", "token-a")
    set_mcp_secret("siem-b", "token-b")
    assert get_mcp_secret("siem-a") == "token-a"
    assert get_mcp_secret("siem-b") == "token-b"
    # different service names — no cross-read API exists
    assert mcp_service("siem-a") != mcp_service("siem-b")
    assert get_secret(mcp_service("siem-a"), "default") == "token-a"
    assert get_secret(mcp_service("siem-b"), "default") != get_secret(
        mcp_service("siem-a"), "default"
    )
    delete_mcp_secret("siem-a")
    assert get_mcp_secret("siem-a") is None
    assert get_mcp_secret("siem-b") == "token-b"


def test_provider_loads_key_from_secrets(secrets_env, monkeypatch):
    monkeypatch.delenv("CYBERGUARD_LLM_API_KEY", raising=False)
    # no provider.json key
    set_provider_api_key("sk-from-store")
    from apps.desktop.sidecar.provider import load_provider_config

    # force live mode via env without key
    monkeypatch.setenv("CYBERGUARD_LLM_MODE", "live")
    monkeypatch.setenv("CYBERGUARD_LLM_BASE_URL", "https://example.invalid/v1")
    cfg = load_provider_config()
    assert cfg.mode == "live"
    assert cfg.api_key == "sk-from-store"
    assert cfg.public_status()["has_api_key"] is True
    # public status must not include raw key
    assert "sk-from-store" not in json.dumps(cfg.public_status())


def test_audit_chain_append_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    r1 = audit_chain.append_event("user_task", {"task": "hello"}, session_id="s1")
    r2 = audit_chain.append_event(
        "tool_call_end",
        {"name": "host_read_file", "error": False},
        session_id="s1",
        run_id="r1",
    )
    assert r1["seq"] == 1
    assert r2["seq"] == 2
    assert r2["prev_hash"] == r1["entry_hash"]
    assert r1["approval_type"] == "self"
    v = audit_chain.verify_chain()
    assert v["ok"] is True
    assert v["count"] == 2
    tail = audit_chain.tail(10)
    assert len(tail) == 2


def test_audit_chain_detects_tamper(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    audit_chain.append_event("user_task", {"task": "a"})
    audit_chain.append_event("answer_ready", {"type": "answer_ready"})
    path = audit_chain.chain_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    # tamper first payload
    obj = json.loads(lines[0])
    obj["payload"]["task"] = "HACKED"
    lines[0] = json.dumps(obj, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = audit_chain.verify_chain()
    assert v["ok"] is False
    assert v["broken_at"] == 1


def test_audit_redacts_secret_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    audit_chain.append_event("test", {"api_key": "sk-should-not-persist", "note": "ok"})
    entry = audit_chain.tail(1)[0]
    assert entry["payload"]["api_key"] == "[redacted]"
    assert entry["payload"]["note"] == "ok"


@pytest.mark.asyncio
async def test_rpc_secrets_and_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    from apps.desktop.sidecar.main import SidecarServer

    stdin = StringIO()
    stdout = StringIO()
    server = SidecarServer(stdin, stdout)

    await server.handle(
        {
            "id": "1",
            "method": "secrets.set_provider_key",
            "params": {"api_key": "sk-rpc-test"},
        }
    )
    await server.handle({"id": "2", "method": "secrets.status", "params": {}})
    await server.handle(
        {
            "id": "3",
            "method": "agent.run",
            "params": {"task": "ping audit", "tier": "readonly"},
        }
    )
    await server.handle({"id": "4", "method": "audit.verify", "params": {}})
    await server.handle({"id": "5", "method": "audit.tail", "params": {"n": 5}})

    lines = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
    by_id = {o["id"]: o for o in lines if "id" in o and ("result" in o or "error" in o)}
    assert by_id["1"]["result"]["ok"] is True
    assert by_id["2"]["result"]["provider_key_present"] is True
    assert by_id["4"]["result"]["ok"] is True
    assert by_id["4"]["result"]["count"] >= 1
    assert len(by_id["5"]["result"]["events"]) >= 1
    # ensure key never appears in any RPC payload
    blob = stdout.getvalue()
    assert "sk-rpc-test" not in blob
