"""Model-authored code goes to the no-network sandbox as a one-file bundle."""
from __future__ import annotations

import base64

import pytest

import app.services.code_runner as cr


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def fake_post(base_url, payload, timeout):
        seen.append({"url": base_url, "payload": payload, "timeout": timeout})
        return {"status": "completed", "stdout": "42", "exit_code": 0, "is_error": False}

    monkeypatch.setattr(cr, "_post_to_runner", fake_post)
    monkeypatch.setattr(cr, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    return seen


@pytest.mark.asyncio
async def test_code_is_sent_as_a_single_main_py(calls):
    result = await cr.run_code("print(6*7)", timeout=20)
    assert result["stdout"] == "42"

    call = calls[-1]
    assert call["payload"]["argv"] == ["python3", "main.py"]
    files = call["payload"]["files"]
    assert len(files) == 1
    assert files[0]["path"] == "main.py"
    assert base64.b64decode(files[0]["content_b64"]).decode() == "print(6*7)"


@pytest.mark.asyncio
async def test_it_never_reaches_the_networked_runner(calls):
    await cr.run_code("print(1)")
    assert calls[-1]["url"] == "http://skill-runner:9000"


@pytest.mark.asyncio
async def test_no_proxy_url_is_ever_sent(calls):
    # Phase 2's allowlist is not available to model-authored code.
    await cr.run_code("print(1)")
    assert "proxy_url" not in calls[-1]["payload"]


@pytest.mark.asyncio
async def test_the_timeout_is_passed_through(calls):
    await cr.run_code("print(1)", timeout=7)
    assert calls[-1]["payload"]["timeout"] == 7
    assert calls[-1]["timeout"] == 7
