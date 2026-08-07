"""The governance gate must cover every tool path, not just the pool tools.

MCP tools, the knowledge base and the OSINT search tools used to call straight
through to their executors: no kill switch, no gatekeeper, no audit row. MCP is
where the dangerous external capabilities live, so it was the one path with no
controls at all.
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner


def _runner(**overrides):
    cfg = {"id": 1, "agent_name": "x", "system_prompt": "", "knowledge_base_id": 9,
           "associated_skills": [], "metadata_json": {"enable_search": True},
           "permission_level": "medium", "autonomy_tier": "L2",
           "allowed_categories": ["observe", "annotate"], "is_poc": True}
    cfg.update(overrides)
    r = InternalAgentRunner(cfg)
    r._mcp_by_name = {}
    r._user_id = 0
    return r


def _call(name, **args):
    return SimpleNamespace(id="c1", function=SimpleNamespace(
        name=name, arguments=json.dumps(args)))


@pytest.fixture
def audit(monkeypatch):
    rec = AsyncMock()
    monkeypatch.setattr("app.core.audit.record_action", rec)
    return rec


@pytest.fixture
def not_halted(monkeypatch):
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=False))


@pytest.fixture
def halted(monkeypatch):
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=True))


# ---- kill switch now reaches every path -------------------------------------

@pytest.mark.asyncio
async def test_kill_switch_stops_kb_search(halted, audit, monkeypatch):
    searched = AsyncMock(return_value=["chunk"])
    monkeypatch.setattr(ia_mod, "knowledge_service", SimpleNamespace(search=searched))

    out = await _runner()._dispatch(_call("kb_search", query="foo"))

    assert out.terminate is True and out.status == "halted"
    searched.assert_not_awaited()


@pytest.mark.asyncio
async def test_kill_switch_stops_web_search(halted, audit, monkeypatch):
    searched = AsyncMock(return_value=[])
    monkeypatch.setattr(ia_mod, "search_service",
                        SimpleNamespace(web_search=searched, vuln_search=AsyncMock()))

    out = await _runner()._dispatch(_call("web_search", query="foo"))

    assert out.terminate is True and out.status == "halted"
    searched.assert_not_awaited()


@pytest.mark.asyncio
async def test_kill_switch_stops_mcp_tool(halted, audit, monkeypatch):
    executed = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.services.mcp_executor.execute_mcp_tool", executed)

    runner = _runner()
    runner._mcp_by_name = {"remote_exec": (
        SimpleNamespace(tool_name="remote_exec", action_category="remediate",
                        risk_tier="high"),
        SimpleNamespace(name="srv"))}

    out = await runner._dispatch(_call("remote_exec", cmd="rm -rf /"))

    assert out.terminate is True and out.status == "halted"
    executed.assert_not_awaited()


# ---- gatekeeper now applies to tagged MCP tools ------------------------------

@pytest.mark.asyncio
async def test_mcp_tool_outside_allowed_categories_is_denied(not_halted, audit,
                                                             monkeypatch):
    executed = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.services.mcp_executor.execute_mcp_tool", executed)

    runner = _runner(allowed_categories=["observe"])
    runner._mcp_by_name = {"isolate": (
        SimpleNamespace(tool_name="isolate", action_category="contain_hard",
                        risk_tier="high"),
        SimpleNamespace(name="srv"))}

    out = await runner._dispatch(_call("isolate", host="h1"))

    assert out.terminate is True and out.status == "denied"
    executed.assert_not_awaited()


@pytest.mark.asyncio
async def test_untagged_mcp_tool_still_runs_but_is_audited(not_halted, audit,
                                                           monkeypatch):
    """Untagged MCP tools default to "observe" so existing deployments keep
    working — the win for those is the kill switch and the audit trail."""
    executed = AsyncMock(return_value={"stdout": "ok"})
    monkeypatch.setattr("app.services.mcp_executor.execute_mcp_tool", executed)

    runner = _runner()
    runner._mcp_by_name = {"lookup": (
        SimpleNamespace(tool_name="lookup", action_category=None, risk_tier=None),
        SimpleNamespace(name="srv"))}

    out = await runner._dispatch(_call("lookup", q="x"))

    executed.assert_awaited_once()
    assert "stdout" in out
    audit.assert_awaited()
    assert audit.await_args.kwargs["action"] == "gatekeeper:allow"


# ---- every decision leaves a record -----------------------------------------

@pytest.mark.asyncio
async def test_allowed_read_tool_is_audited(not_halted, audit, monkeypatch):
    monkeypatch.setattr(ia_mod, "knowledge_service",
                        SimpleNamespace(search=AsyncMock(return_value=["c"])))

    await _runner()._dispatch(_call("kb_search", query="foo"))

    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["action"] == "gatekeeper:allow"
    assert kwargs["action_category"] == "observe"
    assert kwargs["input_data"]["tool"] == "kb_search"


@pytest.mark.asyncio
async def test_refusal_is_audited(halted, audit, monkeypatch):
    monkeypatch.setattr(ia_mod, "knowledge_service",
                        SimpleNamespace(search=AsyncMock()))

    await _runner()._dispatch(_call("kb_search", query="foo"))

    audit.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "gatekeeper:deny"


@pytest.mark.asyncio
async def test_audit_failure_does_not_crash_the_run_but_still_enforces(
        halted, monkeypatch):
    """An unwritable audit row must not become a way to bypass — or crash — the
    gate."""
    monkeypatch.setattr("app.core.audit.record_action",
                        AsyncMock(side_effect=RuntimeError("db down")))
    searched = AsyncMock()
    monkeypatch.setattr(ia_mod, "knowledge_service",
                        SimpleNamespace(search=searched))

    out = await _runner()._dispatch(_call("kb_search", query="foo"))

    assert out.terminate is True and out.status == "halted"
    searched.assert_not_awaited()


# ---- pool tools now pass through the same gate as everything else -----------

def _pool_row(name, category, **kw):
    base = dict(id=1, name=name, description="", input_schema_json=None,
                command_template=f"{name} {{host}}", action_category=category,
                risk_tier="high", rollback_command_template=None,
                permission_level="medium")
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_pool_tool_outside_allowed_categories_is_denied_before_execution(
        not_halted, audit, monkeypatch):
    """Pool tools used to be gated only inside execute_tool. They now clear the
    same before_tool chain as MCP, KB and search."""
    executed = AsyncMock(return_value={"status": "completed", "stdout": "done"})
    monkeypatch.setattr(ia_mod, "execute_tool", executed)

    runner = _runner(allowed_categories=["observe"])
    runner._pool_tools_by_name = {"isolate": _pool_row("isolate", "contain_hard")}

    out = await runner._dispatch(_call("isolate", host="h1"))

    assert out.terminate is True and out.status == "denied"
    executed.assert_not_awaited()


@pytest.mark.asyncio
async def test_kill_switch_stops_pool_tool(halted, audit, monkeypatch):
    executed = AsyncMock(return_value={"status": "completed", "stdout": "done"})
    monkeypatch.setattr(ia_mod, "execute_tool", executed)

    runner = _runner()
    runner._pool_tools_by_name = {"grep": _pool_row("grep", "observe")}

    out = await runner._dispatch(_call("grep", host="h1"))

    assert out.terminate is True and out.status == "halted"
    executed.assert_not_awaited()


@pytest.mark.asyncio
async def test_allowed_pool_tool_runs_with_gatekeeper_disabled_downstream(
        not_halted, audit, monkeypatch):
    """The verdict is rendered once. execute_tool must not re-run it, or every
    gated call would be audited twice and raise two approval requests."""
    executed = AsyncMock(return_value={"status": "completed", "stdout": "3 matches"})
    monkeypatch.setattr(ia_mod, "execute_tool", executed)

    runner = _runner()
    runner._pool_tools_by_name = {"grep": _pool_row("grep", "observe")}

    out = await runner._dispatch(_call("grep", host="h1"))

    assert out.text == "3 matches"
    assert executed.await_args.kwargs["governance"] is None
    assert audit.await_count == 1


@pytest.mark.asyncio
async def test_approval_request_is_raised_by_the_gate(not_halted, audit, monkeypatch):
    """execute_tool no longer sees the NEEDS_APPROVAL verdict, so the gate has to
    raise the request itself."""
    monkeypatch.setattr(ia_mod, "execute_tool", AsyncMock())
    created = AsyncMock()
    monkeypatch.setattr("app.services.approval_service.ApprovalService.create_request",
                        created)

    runner = _runner(allowed_categories=["observe", "remediate"], autonomy_tier="L3",
                     is_poc=False)
    runner._pool_tools_by_name = {"patch": _pool_row("patch", "remediate",
                                                      rollback_command_template="undo {host}")}

    out = await runner._dispatch(_call("patch", host="h1"))

    assert out.status == "needs_approval" and out.terminate is True
    created.assert_awaited_once()
    assert created.await_args.kwargs["payload"]["tool"] == "patch"


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_without_running_hooks(not_halted, audit):
    out = await _runner()._dispatch(_call("no_such_tool"))
    assert out.status == "error"
    assert "unknown tool" in out.text
    audit.assert_not_awaited()          # nothing to govern


@pytest.mark.asyncio
async def test_a_custom_before_tool_hook_can_block(not_halted, audit, monkeypatch):
    """The chain is the extension point: a deployment can add policy without
    editing the dispatcher."""
    monkeypatch.setattr(ia_mod, "knowledge_service",
                        SimpleNamespace(search=AsyncMock(return_value=["c"])))
    runner = _runner()

    async def no_fridays(name, args, target):
        return ia_mod.ToolOutcome("DENIED: not on Fridays", status="denied",
                                  terminate=True, trusted=True)
    runner._before_tool_hooks.append(("no_fridays", no_fridays))

    out = await runner._dispatch(_call("kb_search", query="x"))
    assert out.status == "denied" and "Fridays" in out.text


# ---- degraded-run bookkeeping ------------------------------------------------

def test_degraded_reasons_are_recorded_once_per_kind():
    """A run that loops for six steps is degraded once, not six times.

    The list is surfaced on `answer_ready` and drives the episode success flag;
    repeating a reason per step just makes the record harder to read.
    """
    from app.services.internal_agent import note_degraded

    reasons = []
    note_degraded(reasons, "tool_call_loop")
    note_degraded(reasons, "budget_exhausted")
    note_degraded(reasons, "tool_call_loop")
    assert reasons == ["tool_call_loop", "budget_exhausted"]
