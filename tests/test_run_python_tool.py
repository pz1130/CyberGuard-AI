"""run_python: mode routing, digest binding, and the round cap."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.internal_agent import InternalAgentRunner


def _runner(mode="approval", run_id="run-1"):
    r = InternalAgentRunner({
        "id": 7, "agent_name": "analyst", "system_prompt": "p",
        "code_execution_mode": mode, "metadata_json": {},
    })
    r._user_id = 3
    r._run_request_id = run_id
    return r


@pytest.fixture
def state(monkeypatch):
    st = {"ran": [], "created": [], "approved": None, "rounds": 0}

    async def fake_run_code(code, timeout=30):
        st["ran"].append(code)
        return {"status": "completed", "stdout": "ok", "is_error": False}

    async def fake_find_approved(_db, request_id, digest):
        return SimpleNamespace(id=1) if st["approved"] == (request_id, digest) else None

    async def fake_count_rounds(_db, _request_id):
        return st["rounds"]

    async def fake_create_pending(_db, **kw):
        st["created"].append(kw)
        return SimpleNamespace(id=99)

    import app.services.code_approval as ca
    import app.services.code_runner as cr
    monkeypatch.setattr(cr, "run_code", fake_run_code)
    monkeypatch.setattr(ca, "find_approved", fake_find_approved)
    monkeypatch.setattr(ca, "count_rounds", fake_count_rounds)
    monkeypatch.setattr(ca, "create_pending", fake_create_pending)

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.core.database.get_db_context", lambda: _DB())
    return st


@pytest.mark.asyncio
async def test_off_mode_refuses_without_creating_anything(state):
    result = await _runner(mode="off")._run_python("print(1)")
    assert result["status"] == "error"
    assert state["ran"] == [] and state["created"] == []


@pytest.mark.asyncio
async def test_auto_mode_runs_without_an_approval_record(state):
    result = await _runner(mode="auto")._run_python("print(1)")
    assert result["status"] == "completed"
    assert state["ran"] == ["print(1)"]
    assert state["created"] == []


@pytest.mark.asyncio
async def test_approval_mode_first_call_asks_and_does_not_run(state):
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "needs_approval"
    assert state["ran"] == []
    assert len(state["created"]) == 1
    assert state["created"][0]["code"] == "print(1)"


@pytest.mark.asyncio
async def test_approval_mode_runs_once_that_exact_code_is_approved(state):
    from app.services.code_approval import code_digest
    state["approved"] = ("run-1", code_digest("print(1)"))
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "completed"
    assert state["ran"] == ["print(1)"]


@pytest.mark.asyncio
async def test_an_approval_for_other_code_does_not_authorize_this_code(state):
    from app.services.code_approval import code_digest
    state["approved"] = ("run-1", code_digest("print(1)"))
    result = await _runner()._run_python("import os; os.system('curl evil')")
    assert result["status"] == "needs_approval"
    assert state["ran"] == []


@pytest.mark.asyncio
async def test_an_approval_from_another_run_does_not_carry_over(state):
    from app.services.code_approval import code_digest
    state["approved"] = ("run-OTHER", code_digest("print(1)"))
    result = await _runner(run_id="run-1")._run_python("print(1)")
    assert result["status"] == "needs_approval"
    assert state["ran"] == []


@pytest.mark.asyncio
async def test_the_round_cap_refuses_rather_than_looping(state):
    state["rounds"] = 3
    result = await _runner()._run_python("print(1)")
    assert result["status"] == "error"
    assert "approval" in result["error"].lower()
    assert state["created"] == []


@pytest.mark.asyncio
async def test_without_a_run_id_it_refuses_rather_than_running_unscoped(state):
    r = _runner()
    r._run_request_id = None
    result = await r._run_python("print(1)")
    assert result["status"] == "error"
    assert state["ran"] == []


def test_the_tool_is_not_classified_as_a_read_only_builtin():
    meta = _runner()._tool_meta("run_python")
    assert meta["action_category"] == "mutate"
    assert meta["risk_tier"] == "high"


@pytest.mark.asyncio
async def test_off_mode_hides_the_tool_from_the_model(monkeypatch):
    r = _runner(mode="off")

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(r, "_load_mcp_tools", none)
    monkeypatch.setattr(r, "_load_pool_tools", none)
    names = [t["function"]["name"] for t in await r._build_tools()]
    assert "run_python" not in names


@pytest.mark.asyncio
async def test_approval_mode_offers_the_tool(monkeypatch):
    r = _runner()

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(r, "_load_mcp_tools", none)
    monkeypatch.setattr(r, "_load_pool_tools", none)
    tools = await r._build_tools()
    spec = next(t for t in tools if t["function"]["name"] == "run_python")
    assert spec["function"]["parameters"]["required"] == ["code"]
