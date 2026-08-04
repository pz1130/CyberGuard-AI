"""Tests for the agent_wrapper broker service."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import agent_wrapper as aw
from app.services.gatekeeper import GovernanceContext


def _agent(**kw):
    base = dict(id=3, agent_name="remote-ir", kind="external", governed=True,
                autonomy_tier="L2", allowed_categories=["observe", "contain_hard"],
                escalate_to_human_below=0.60, is_poc=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_governance_for_external_unwrapped_when_not_governed():
    ctx = aw.governance_for_external(_agent(governed=False))
    assert isinstance(ctx, GovernanceContext) and ctx.external_unwrapped is True


def test_governance_for_external_wrapped_when_governed():
    ctx = aw.governance_for_external(_agent(governed=True))
    assert ctx.external_unwrapped is False


@pytest.mark.asyncio
async def test_broker_execute_routes_through_execute_tool():
    tool = SimpleNamespace(id=9, name="isolate", action_category="contain_hard",
                           rollback_command_template="unisolate {host}")
    with patch.object(aw, "execute_tool", AsyncMock(return_value={"status": "completed"})) as et:
        res = await aw.broker_execute(_agent(), tool, user_id=7,
                                      args={"host": "h1"}, confidence=0.9)
    assert res["status"] == "completed"
    _, kwargs = et.call_args
    assert isinstance(kwargs["governance"], GovernanceContext)
    assert kwargs["confidence"] == 0.9
