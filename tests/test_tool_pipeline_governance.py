"""INV-28: every tool path is gated by `before_tool_call`, not just pool tools.

`agent_core.pipeline` exists and `_dispatch` routes through it, but no
`before_tool_call` was supplied — the hook defaulted to a no-op. So MCP tools,
`kb_search` and `web_search` reached their executors with no kill switch, no
gatekeeper and no audit row. MCP is where the dangerous external capability
lives, which made it the one path with no controls at all (audit #5).

The gate must be provable per-path, so each transport gets its own case.
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import internal_agent as ia_mod
from app.services.internal_agent import InternalAgentRunner


def _runner(**overrides):
    cfg = {
        "id": 1, "agent_name": "gated", "system_prompt": "",
        "knowledge_base_id": 9, "associated_skills": [],
        "metadata_json": {"enable_search": True},
        "permission_level": "medium", "autonomy_tier": "L2",
        "allowed_categories": ["observe", "annotate"], "is_poc": True,
    }
    cfg.update(overrides)
    r = InternalAgentRunner(cfg)
    r._mcp_by_name = {}
    r._user_id = 0
    return r


def _call(name, **args):
    return SimpleNamespace(
        id="c1", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


@pytest.fixture
def halted(monkeypatch):
    """Kill switch engaged — nothing may execute."""
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=True))
    monkeypatch.setattr("app.core.audit.record_action", AsyncMock())


def _is_refusal(result) -> bool:
    """Structured refusal, per INV-32 (no string-prefix sniffing)."""
    if isinstance(result, dict):
        return bool(result.get("is_error")) or result.get("status") in (
            "denied", "halted", "needs_approval")
    return False


@pytest.mark.asyncio
async def test_mcp_tool_is_refused_when_the_kill_switch_is_engaged(halted, monkeypatch):
    r = _runner()
    r._mcp_by_name = {
        "nmap_scan": (SimpleNamespace(tool_name="nmap_scan", action_category="observe",
                                       risk_tier="low"),
                      SimpleNamespace(id=1, name="srv")),
    }
    executed = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.services.mcp_executor.execute_mcp_tool", executed)

    result = await r._dispatch(_call("nmap_scan", target="10.0.0.1"))

    executed.assert_not_awaited()
    assert _is_refusal(result), result


@pytest.mark.asyncio
async def test_kb_search_is_refused_when_the_kill_switch_is_engaged(halted, monkeypatch):
    r = _runner()
    searched = AsyncMock(return_value=[{"chunk": "x"}])
    monkeypatch.setattr(ia_mod.knowledge_service, "search", searched)

    result = await r._dispatch(_call("kb_search", query="q"))

    searched.assert_not_awaited()
    assert _is_refusal(result), result


@pytest.mark.asyncio
async def test_web_search_is_refused_when_the_kill_switch_is_engaged(halted, monkeypatch):
    r = _runner()
    searched = AsyncMock(return_value=[{"title": "x"}])
    monkeypatch.setattr(ia_mod.search_service, "web_search", searched)

    result = await r._dispatch(_call("web_search", query="q"))

    searched.assert_not_awaited()
    assert _is_refusal(result), result


@pytest.mark.asyncio
async def test_every_gate_decision_is_audited(monkeypatch):
    """A refusal has to be provable after the fact, not just effective."""
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=True))
    audited = AsyncMock()
    monkeypatch.setattr("app.core.audit.record_action", audited)
    monkeypatch.setattr(ia_mod.knowledge_service, "search", AsyncMock())

    r = _runner()
    await r._dispatch(_call("kb_search", query="q"))

    audited.assert_awaited()
    action = audited.await_args.kwargs.get("action", "")
    assert "gatekeeper" in action, action


@pytest.mark.asyncio
async def test_an_allowed_observe_tool_still_runs(monkeypatch):
    """The gate must not become a blanket refusal."""
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=False))
    monkeypatch.setattr("app.core.audit.record_action", AsyncMock())
    searched = AsyncMock(return_value=[{"chunk": "hit"}])
    monkeypatch.setattr(ia_mod.knowledge_service, "search", searched)

    r = _runner()
    result = await r._dispatch(_call("kb_search", query="q"))

    searched.assert_awaited_once()
    assert not _is_refusal(result), result


@pytest.mark.asyncio
async def test_preapproved_pool_tool_keeps_rollback_and_spends_approval_once(monkeypatch):
    """The outer gate must pass rollback + approval into pool execution."""
    monkeypatch.setattr("app.services.kill_switch.is_halted",
                        AsyncMock(return_value=False))
    monkeypatch.setattr("app.core.audit.record_action", AsyncMock())
    executed = AsyncMock(return_value={"status": "completed", "stdout": "SIMULATED deny"})
    monkeypatch.setattr(ia_mod, "execute_tool", executed)

    r = _runner(
        permission_level="high",
        allowed_categories=["contain_hard"],
        is_poc=False,
    )
    r._pre_approved = True
    r._pool_tools_by_name = {
        "simulate_block_ip": SimpleNamespace(
            name="simulate_block_ip",
            action_category="contain_hard",
            risk_tier="high",
            permission_level="high",
            rollback_command_template="echo allow {ip}",
        )
    }

    result = await r._dispatch(_call("simulate_block_ip", ip="192.0.2.123"))

    assert not _is_refusal(result), result
    assert r._pre_approved is False
    executed.assert_awaited_once()
    assert executed.await_args.kwargs["approved"] is True
