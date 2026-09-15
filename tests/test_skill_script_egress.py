"""Allowlist executions grant before dispatch and revoke afterwards."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tool_executor as te


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"stdout": "ok", "stderr": "", "exit_code": 0,
                                    "duration_ms": 5, "timed_out": False}
        self.text = "ok"

    def json(self):
        return self._payload


class _Client:
    calls: list = []
    run_status: int = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.calls.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/run"):
            return _Resp(status_code=_Client.run_status)
        return _Resp(payload={"ok": True})


def _tool(**over):
    base = dict(
        name="triage", source_skill_id=7, source_script_path="scripts/x.py",
        source_bundle_digest=None, script_network="allowlist",
        script_network_allowlist=["vendor.example"],
        command_template="python3 scripts/x.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


FILES = [("scripts/x.py", b"print('ok')")]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _Client.calls = []
    _Client.run_status = 200
    monkeypatch.setattr(te.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(te, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    monkeypatch.setattr(te, "SKILL_RUNNER_NET_URL", "http://skill-runner-net:9000")
    monkeypatch.setattr(te, "EGRESS_PROXY_URL", "egress-proxy:3128")
    monkeypatch.setattr(te, "EGRESS_PROXY_CONTROL_URL", "http://egress-proxy:3129")
    monkeypatch.setattr(te, "EGRESS_PROXY_TOKEN", "control-token")
    monkeypatch.setattr(te, "SKILL_RUNNER_TOKEN", "skill-token")

    async def _load(_skill_id):
        return FILES
    monkeypatch.setattr(te, "_load_bundle_for_tool", _load)


def _digest():
    from app.services import skill_bundle
    return skill_bundle.bundle_digest(FILES)


@pytest.mark.asyncio
async def test_allowlist_run_grants_dispatches_then_revokes():
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "completed"

    urls = [c["url"] for c in _Client.calls]
    assert urls == ["http://egress-proxy:3129/grant",
                    "http://skill-runner-net:9000/run",
                    "http://egress-proxy:3129/revoke"]

    grant, run, revoke = _Client.calls
    assert grant["headers"]["X-Egress-Token"] == "control-token"
    assert grant["json"]["allowlist"] == ["vendor.example"]
    assert grant["json"]["ttl"] == 30 + te.GRANT_TTL_MARGIN_SECONDS
    nonce = grant["json"]["nonce"]
    assert len(nonce) >= 32
    assert run["json"]["proxy_url"] == f"http://{nonce}:x@egress-proxy:3128"
    assert "X-Egress-Token" not in run["headers"]
    assert revoke["json"]["nonce"] == nonce


@pytest.mark.asyncio
async def test_each_execution_gets_a_fresh_nonce():
    tool = _tool(source_bundle_digest=_digest())
    ctx = SimpleNamespace(tool=tool, user_id=1, metadata={})
    await te._pool_execute(ctx, {"target": "x"})
    await te._pool_execute(ctx, {"target": "x"})
    nonces = [c["json"]["nonce"] for c in _Client.calls if c["url"].endswith("/grant")]
    assert len(nonces) == 2 and nonces[0] != nonces[1]


@pytest.mark.asyncio
async def test_revoke_happens_even_when_the_run_fails():
    _Client.run_status = 500
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert [c["url"] for c in _Client.calls][-1] == "http://egress-proxy:3129/revoke"


@pytest.mark.asyncio
async def test_a_none_tool_never_touches_the_proxy():
    result = await te._pool_execute(
        SimpleNamespace(
            tool=_tool(script_network="none", script_network_allowlist=None,
                       source_bundle_digest=_digest()),
            user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "completed"
    assert [c["url"] for c in _Client.calls] == ["http://skill-runner:9000/run"]


@pytest.mark.asyncio
async def test_allowlist_without_hosts_refuses_rather_than_running_unscoped():
    result = await te._pool_execute(
        SimpleNamespace(
            tool=_tool(script_network_allowlist=[], source_bundle_digest=_digest()),
            user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert "allowlist" in result["error"].lower()
    assert _Client.calls == []


@pytest.mark.asyncio
async def test_a_failed_grant_refuses_rather_than_running_without_network(monkeypatch):
    class _Failing(_Client):
        async def post(self, url, json=None, headers=None):
            _Client.calls.append({"url": url, "json": json, "headers": headers})
            if url.endswith("/grant"):
                raise RuntimeError("proxy unreachable")
            return _Resp()

    monkeypatch.setattr(te.httpx, "AsyncClient", _Failing)
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest=_digest()), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert "egress" in result["error"].lower()
    assert not any(c["url"].endswith("/run") for c in _Client.calls)


@pytest.mark.asyncio
async def test_a_changed_bundle_refuses_before_any_grant_is_made():
    result = await te._pool_execute(
        SimpleNamespace(tool=_tool(source_bundle_digest="a" * 64), user_id=1, metadata={}),
        {"target": "x"})
    assert result["status"] == "error"
    assert "approval" in result["error"].lower()
    assert _Client.calls == []
