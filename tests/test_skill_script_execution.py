"""Skill scripts take the same gate chain and a different runner."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tool_executor as te


class _Resp:
    status_code = 200

    @staticmethod
    def json():
        return {"stdout": "ok", "stderr": "", "exit_code": 0,
                "duration_ms": 5, "timed_out": False}


class _Client:
    """Records where the executor posted and what it sent."""

    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.calls.append({"url": url, "json": json, "headers": headers})
        return _Resp()


def _script_tool(**over):
    base = dict(
        name="triage-script", source_skill_id=7, source_script_path="scripts/x.py",
        source_bundle_digest=None, script_network="none",
        command_template="python3 scripts/x.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(te.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(te, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    monkeypatch.setattr(te, "SKILL_RUNNER_TOKEN", "skill-token")
    monkeypatch.setattr(te, "TOOL_RUNNER_URL", "http://tool-runner:9000")
    monkeypatch.setattr(te, "RUNNER_TOKEN", "tool-token")


def _loader(files):
    async def _load(_skill_id):
        return files

    return _load


@pytest.mark.asyncio
async def test_a_script_tool_goes_to_the_skill_runner_with_its_bundle(monkeypatch):
    files = [("scripts/x.py", b"print('ok')"), ("refs/a.md", b"doc")]
    from app.services import skill_bundle

    digest = skill_bundle.bundle_digest(files)
    monkeypatch.setattr(te, "_load_bundle_for_tool", _loader(files))

    tool = _script_tool(source_bundle_digest=digest)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "1.2.3.4"})

    assert result["status"] == "completed"
    call = _Client.calls[-1]
    assert call["url"] == "http://skill-runner:9000/run"
    assert call["headers"]["X-Skill-Runner-Token"] == "skill-token"
    assert "X-Runner-Token" not in call["headers"]
    assert call["json"]["argv"] == ["python3", "scripts/x.py", "1.2.3.4"]
    assert {f["path"] for f in call["json"]["files"]} == {"scripts/x.py", "refs/a.md"}


@pytest.mark.asyncio
async def test_a_changed_bundle_refuses_to_execute(monkeypatch):
    monkeypatch.setattr(
        te, "_load_bundle_for_tool", _loader([("scripts/x.py", b"print('EVIL')")]))

    tool = _script_tool(source_bundle_digest="a" * 64)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "x"})

    assert result["status"] == "error"
    assert "approval" in result["error"].lower()
    assert _Client.calls == []  # nothing was sent anywhere


@pytest.mark.asyncio
async def test_an_ordinary_tool_still_goes_to_the_tool_runner():
    tool = SimpleNamespace(
        name="nmap-scan", source_skill_id=None, command_template="nmap {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "1.2.3.4"})

    assert result["status"] == "completed"
    call = _Client.calls[-1]
    assert call["url"] == "http://tool-runner:9000/run"
    assert call["headers"]["X-Runner-Token"] == "tool-token"
    assert "files" not in call["json"]
