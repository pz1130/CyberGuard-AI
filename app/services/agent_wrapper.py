"""Wrap external/black-box agents: route their tool calls through the governed
execute_tool() chokepoint (NDB Std §Scope — black-box agents must be wrapped)."""
from __future__ import annotations
from app.services.gatekeeper import GovernanceContext
from app.services.governance_config import load_governance
from app.services.tool_executor import execute_tool


def governance_for_external(agent) -> GovernanceContext:
    """Like load_governance, but marks external+un-governed agents as un-wrapped
    so the gatekeeper caps them to read-only/notify."""
    ctx = load_governance(agent)
    kind = getattr(agent, "kind", "external")
    ctx.external_unwrapped = (kind == "external") and not bool(getattr(agent, "governed", False))
    return ctx


async def broker_execute(agent, tool, user_id: int, args: dict, confidence: float | None) -> dict:
    """Execute one tool on behalf of a wrapped agent through the governed path."""
    governance = governance_for_external(agent)
    return await execute_tool(tool, args, user_id=user_id,
                              governance=governance, confidence=confidence)
