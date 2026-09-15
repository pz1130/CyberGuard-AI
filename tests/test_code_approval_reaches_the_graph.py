"""The link that was missing: a tool's needs_approval must become the run's.

The earlier tests covered both ends and skipped the middle. `_validation_node`
was tested given `approval_required` already set, and `_run_python` was tested
by calling it directly. Neither exercised the one hop in between — the runner
reporting that a tool asked for approval — and that hop was not implemented, so
the graph never suspended and the approval record was orphaned.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.master import MasterAgent
from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner


@pytest.fixture(autouse=True)
def _quiet_gates(monkeypatch):
    """This file is about status propagation, not the audit chain."""
    async def noop(*_a, **_kw):
        return {}

    async def not_halted(*_a, **_kw):
        return False

    monkeypatch.setattr("app.core.audit.record_action", noop)
    monkeypatch.setattr("app.services.kill_switch.is_halted", not_halted)


def _permissive_cfg(**over):
    """An agent a deployment has actually allowed to run code.

    run_python is classified `mutate`, which the gatekeeper denies three ways
    by default: forbidden in a POC, below the L3 autonomy floor, and absent
    from DEFAULT_ALLOWED. Enabling it is three deliberate settings, which is
    the point — see test_the_default_poc_deployment_refuses_it.
    """
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium", "code_execution_mode": "approval",
           "is_poc": False, "autonomy_tier": "L3",
           "allowed_categories": ["observe", "annotate", "mutate"]}
    cfg.update(over)
    return cfg


def _tool_call(name, cid, arguments):
    return SimpleNamespace(
        id=cid, function=SimpleNamespace(name=name, arguments=arguments))


@pytest.mark.asyncio
async def test_a_tool_asking_for_approval_makes_the_whole_run_ask(monkeypatch):
    """run_python returns needs_approval -> execute() must not report completed."""
    step1 = SimpleNamespace(
        content="",
        tool_calls=[_tool_call("run_python", "1", '{"code": "print(1)"}')])
    fake_router = SimpleNamespace(
        chat=AsyncMock(side_effect=[step1, "I need approval to run that."]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    runner = InternalAgentRunner(_permissive_cfg())

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(runner, "_load_mcp_tools", none)
    monkeypatch.setattr(runner, "_load_pool_tools", none)

    # Stub what _run_python depends on rather than _run_python itself: the
    # method under test is the one that has to record the pending approval.
    import app.services.code_approval as ca
    import app.services.code_runner as cr

    async def never_approved(_db, _run, _digest):
        return None

    async def no_rounds_yet(_db, _run):
        return 0

    async def fake_create(_db, **_kw):
        return SimpleNamespace(id=1)

    async def must_not_run(_code, timeout=30):
        raise AssertionError("unapproved code must never reach the sandbox")

    monkeypatch.setattr(ca, "find_approved", never_approved)
    monkeypatch.setattr(ca, "count_rounds", no_rounds_yet)
    monkeypatch.setattr(ca, "create_pending", fake_create)
    monkeypatch.setattr(cr, "run_code", must_not_run)

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.core.database.get_db_context", lambda: _DB())

    result = await runner.execute(task="compute something", conversation_id=None,
                                  user_id=1, run_request_id="run-1")

    assert result["status"] == "needs_approval", (
        "the runner reported completed, so master never sets approval_required "
        "and the graph never suspends"
    )


@pytest.mark.asyncio
async def test_a_run_with_no_such_tool_still_completes(monkeypatch):
    fake_router = SimpleNamespace(chat=AsyncMock(side_effect=["done"]))
    monkeypatch.setattr(ia_mod, "get_llm_router", lambda: fake_router)

    cfg = {"id": 1, "agent_name": "x", "system_prompt": "sys", "llm_provider_id": 1,
           "llm_model": "m", "tool_loop_max_steps": 4, "memory_window": 0,
           "associated_skills": [], "metadata_json": {"mcp_tool_ids": []},
           "permission_level": "medium", "code_execution_mode": "off"}
    runner = InternalAgentRunner(cfg)

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(runner, "_load_mcp_tools", none)
    monkeypatch.setattr(runner, "_load_pool_tools", none)

    result = await runner.execute(task="hi", conversation_id=None, user_id=1)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_the_graph_turns_that_status_into_a_suspension():
    """The other half of the hop: master must act on the reported status."""
    agent = MasterAgent.__new__(MasterAgent)
    state = {
        "sub_results": {"analyst": {"status": "needs_approval", "output": None}},
        "task_plan": [],
    }
    out = await MasterAgent._validation_node(agent, state)
    assert out["approval_required"] is True
    assert MasterAgent._validation_decision(MasterAgent, out) == "rejected"


@pytest.mark.asyncio
async def test_a_completed_sub_result_does_not_suspend_the_graph():
    agent = MasterAgent.__new__(MasterAgent)
    state = {
        "sub_results": {"analyst": {"status": "completed", "output": "42"}},
        "task_plan": [],
    }
    out = await MasterAgent._validation_node(agent, state)
    assert not out.get("approval_required")
    assert MasterAgent._validation_decision(MasterAgent, out) == "approved"


@pytest.mark.asyncio
async def test_the_default_poc_deployment_refuses_it(monkeypatch):
    """A default deployment denies run_python at the gatekeeper, loudly.

    `mutate` is forbidden in a POC, and running code a model just wrote is a
    mutating capability however the run turns out. The operator turns it on
    deliberately; until then the model gets a reason, not a silent no-op.
    """
    step1 = SimpleNamespace(
        content="",
        tool_calls=[_tool_call("run_python", "1", '{"code": "print(1)"}')])
    monkeypatch.setattr(
        ia_mod, "get_llm_router",
        lambda: SimpleNamespace(chat=AsyncMock(side_effect=[step1, "blocked"])))

    # Default governance: is_poc True, tier L2, DEFAULT_ALLOWED categories.
    runner = InternalAgentRunner(_permissive_cfg(
        is_poc=True, autonomy_tier="L2", allowed_categories=None))

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(runner, "_load_mcp_tools", none)
    monkeypatch.setattr(runner, "_load_pool_tools", none)

    import app.services.code_runner as cr

    async def must_not_run(_code, timeout=30):
        raise AssertionError("the gatekeeper should have stopped this")

    monkeypatch.setattr(cr, "run_code", must_not_run)

    result = await runner.execute(task="t", conversation_id=None, user_id=1,
                                  run_request_id="run-1")
    refusal = result["tool_calls"][0]["result_preview"]
    assert "mutate" in refusal and "POC" in refusal


@pytest.mark.asyncio
async def test_any_gated_tool_makes_the_run_ask_not_just_run_python(monkeypatch):
    """The gap was never specific to run_python.

    Every tool the gatekeeper sends to approval used to leave the run reporting
    "completed", so the record it opened had nothing to resume. Asserted on the
    contract itself rather than through one tool, so it does not depend on
    which categories a particular deployment happens to allow.
    """
    runner = InternalAgentRunner(_permissive_cfg())

    async def no_record(*_a, **_kw):
        return None

    monkeypatch.setattr(runner, "_request_approval", no_record)
    monkeypatch.setattr(
        runner, "_tool_meta",
        lambda _n: {"action_category": "remediate", "risk_tier": "high",
                    # Without a rollback the envelope rule denies outright; this
                    # test wants the approval branch, not the deny branch.
                    "has_rollback": True, "transport": "builtin"})
    runner._governance_cfg["allowed_categories"] = ["observe", "remediate"]

    assert runner._pending_approval_reason is None
    blocked = await runner._before_tool_call(
        SimpleNamespace(tool_name="some_tool", tool=None, user_id=1, metadata={}),
        {"target": "x"})

    assert blocked is not None and blocked.reason == "needs_approval"
    assert runner._pending_approval_reason, (
        "the run must report needs_approval, or the record it just opened has "
        "nothing to resume"
    )


@pytest.mark.asyncio
async def test_the_generic_gate_does_not_pre_empt_the_code_specific_one(monkeypatch):
    """An approval that does not show the code is worse than no approval.

    The gatekeeper escalates run_python on confidence before _run_python ever
    runs. If that short-circuited, the record a human sees would carry no code
    and no digest — a blind approval — and the code-carrying record would only
    appear a round later.
    """
    proposed = []

    step1 = SimpleNamespace(
        content="",
        tool_calls=[_tool_call("run_python", "1", '{"code": "print(1)"}')])
    monkeypatch.setattr(
        ia_mod, "get_llm_router",
        lambda: SimpleNamespace(chat=AsyncMock(side_effect=[step1, "waiting"])))

    runner = InternalAgentRunner(_permissive_cfg())

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(runner, "_load_mcp_tools", none)
    monkeypatch.setattr(runner, "_load_pool_tools", none)

    import app.services.code_approval as ca
    import app.services.code_runner as cr

    async def never_approved(*_a, **_kw):
        return None

    async def no_rounds(*_a, **_kw):
        return 0

    async def record_it(_db, **kw):
        proposed.append(kw["code"])
        return SimpleNamespace(id=1)

    async def must_not_run(_code, timeout=30):
        raise AssertionError("unapproved code must never reach the sandbox")

    monkeypatch.setattr(ca, "find_approved", never_approved)
    monkeypatch.setattr(ca, "count_rounds", no_rounds)
    monkeypatch.setattr(ca, "create_pending", record_it)
    monkeypatch.setattr(cr, "run_code", must_not_run)

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.core.database.get_db_context", lambda: _DB())

    result = await runner.execute(task="t", conversation_id=None, user_id=1,
                                  run_request_id="run-1")

    assert result["status"] == "needs_approval"
    assert proposed == ["print(1)"], (
        "the code-carrying approval was never opened, so a reviewer would be "
        "asked to approve something they cannot see"
    )


@pytest.mark.asyncio
async def test_a_denied_category_still_short_circuits(monkeypatch):
    """Falling through is only for approval, never for a denial."""
    step1 = SimpleNamespace(
        content="",
        tool_calls=[_tool_call("run_python", "1", '{"code": "print(1)"}')])
    monkeypatch.setattr(
        ia_mod, "get_llm_router",
        lambda: SimpleNamespace(chat=AsyncMock(side_effect=[step1, "blocked"])))

    runner = InternalAgentRunner(_permissive_cfg(
        is_poc=True, autonomy_tier="L2", allowed_categories=None))

    async def none(*_a, **_kw):
        return []

    monkeypatch.setattr(runner, "_load_mcp_tools", none)
    monkeypatch.setattr(runner, "_load_pool_tools", none)

    import app.services.code_approval as ca

    async def must_not_be_called(*_a, **_kw):
        raise AssertionError("a denied call must not open an approval")

    monkeypatch.setattr(ca, "create_pending", must_not_be_called)

    result = await runner.execute(task="t", conversation_id=None, user_id=1,
                                  run_request_id="run-1")
    assert "POC" in result["tool_calls"][0]["result_preview"]
