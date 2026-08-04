"""Executable Tool pool — validate args, build an injection-safe argv, and run
it in the isolated tool-runner container. See:
  docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md

M0a-2: schema validation runs in the pipeline (INV-30); build_argv still
validates placeholders. Results include ``is_error`` (INV-32).
"""
import json
import os
import shlex
import uuid
from typing import Any, Dict, List, Optional

import httpx

from agent_core.pipeline import BlockedResult, ToolCallContext, run_tool_call
from agent_core.schema_validate import SchemaValidationError, validate_tool_arguments


TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_CHARS = 8000  # mirror internal_agent.TOOL_RESULT_MAX_CHARS
# Shell / scanner outputs often put signal at the end (errors, findings).
# mode "head" drops the start and keeps the tail (see agent_core.truncate).
OUTPUT_TRUNCATE_MODE = "head"


class ToolArgError(ValueError):
    """Raised when supplied args don't satisfy the tool's input schema/template."""


def build_argv(command_template: str, input_schema: Optional[Dict[str, Any]],
               args: Dict[str, Any]) -> List[str]:
    """Turn a command template + args into a safe argv list.

    Placeholders must be standalone `{name}` tokens whose name is declared in the
    schema's properties; each becomes a single argv element (never shell-parsed),
    making command injection structurally impossible.
    """
    schema = input_schema or {}
    try:
        args = validate_tool_arguments(args, schema if schema.get("properties") else schema)
    except SchemaValidationError as e:
        raise ToolArgError(str(e)) from e

    props = schema.get("properties", {}) or {}

    if not command_template:
        raise ToolArgError("tool has no command_template")

    argv: List[str] = []
    for tok in shlex.split(command_template):
        if len(tok) >= 2 and tok[0] == "{" and tok[-1] == "}":
            name = tok[1:-1]
            if name not in props:
                raise ToolArgError(f"placeholder {tok} not in schema")
            if name not in args:
                raise ToolArgError(f"unfilled placeholder: {name!r}")
            argv.append(str(args[name]))
        elif "{" in tok or "}" in tok:
            raise ToolArgError(f"placeholder must be a standalone token, got {tok!r}")
        else:
            argv.append(tok)
    return argv


def _truncate(text: str, *, mode: str = OUTPUT_TRUNCATE_MODE) -> str:
    """Directional truncate for tool-runner stdout/stderr (roadmap #10)."""
    from agent_core.truncate import truncate_tool_result

    return truncate_tool_result(
        text or "",
        max_chars=OUTPUT_MAX_CHARS,
        mode="head" if mode == "head" else "tail",
    )


async def _create_approval(tool, args: Dict[str, Any], user_id: int) -> None:
    from app.services.approval_service import ApprovalService
    await ApprovalService().create_request(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        action_type="tool.execute",
        action_description=f"Execute tool {getattr(tool, 'name', '?')}",
        payload={"tool": getattr(tool, "name", None), "args": args},
        risk_level=getattr(tool, "risk_tier", None) or "high",
    )


async def _pool_before_tool_call(
    ctx: ToolCallContext, args: Dict[str, Any]
) -> Optional[BlockedResult]:
    """Gates that historically ran before the tool-runner call (behavior preserved)."""
    tool = ctx.tool
    user_id = ctx.user_id or 0
    meta = ctx.metadata
    approved = bool(meta.get("approved"))
    caller_permissions = meta.get("caller_permissions")
    governance = meta.get("governance")
    confidence = meta.get("confidence")

    # Kill switch — hardest gate, checked before anything else (NDB Std §Kill Switch).
    from app.services.kill_switch import is_halted
    if await is_halted(agent_id=getattr(tool, "agent_id", None)):
        from app.core.audit import record_action
        await record_action(user_id=user_id, agent_name=getattr(tool, "name", None),
                            action="EMERGENCY_HALT", action_category=getattr(tool, "action_category", None),
                            input_data={"tool": getattr(tool, "name", None), "args": args},
                            output_data={"blocked": True})
        return BlockedResult(
            payload={"status": "halted", "error": "kill switch engaged"},
            reason="kill_switch",
        )

    # RBAC: only enforced when caller_permissions is provided (API path). The
    # internal-agent path passes None — assignment to the agent is the authorization.
    req = getattr(tool, "required_permission", None)
    if req and caller_permissions is not None and req not in caller_permissions:
        return BlockedResult(
            payload={"status": "error", "error": f"missing required permission: {req}"},
            reason="rbac",
        )

    # --- Governance gatekeeper (NDB Std §Action Gatekeeper) ---
    if governance is not None:
        from app.services.gatekeeper import gatekeeper_check, Decision
        from app.core.audit import record_action
        tool_meta = {"action_category": getattr(tool, "action_category", None),
                     "risk_tier": getattr(tool, "risk_tier", None),
                     "has_rollback": bool(getattr(tool, "rollback_command_template", None))}
        verdict = gatekeeper_check(tool_meta, governance, confidence=confidence)
        await record_action(
            user_id=user_id, agent_name=getattr(tool, "name", None),
            action=f"gatekeeper:{verdict.decision.value}",
            action_category=verdict.category, risk_tier=verdict.risk_tier,
            confidence=confidence, rollback_possible=None,
            input_data={"tool": getattr(tool, "name", None), "args": args},
            output_data={"decision": verdict.decision.value, "reason": verdict.reason},
        )
        if verdict.decision is Decision.DENY:
            return BlockedResult(
                payload={"status": "denied", "error": verdict.reason},
                reason="gatekeeper_deny",
            )
        if verdict.decision is Decision.NEEDS_APPROVAL and not approved:
            await _create_approval(tool, args, user_id)
            return BlockedResult(
                payload={"status": "needs_approval", "error": verdict.reason},
                reason="gatekeeper_approval",
            )

    # Approval gate for high-permission tools.
    if getattr(tool, "permission_level", "medium") == "high" and not approved:
        await _create_approval(tool, args, user_id)
        return BlockedResult(
            payload={"status": "needs_approval",
                     "error": "High-permission tool requires approval"},
            reason="high_permission",
        )

    return None


async def _pool_execute(ctx: ToolCallContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Build argv + run tool-runner (+ safety envelope). Unchanged semantics."""
    tool = ctx.tool
    try:
        schema = json.loads(tool.input_schema_json) if tool.input_schema_json else {}
    except json.JSONDecodeError:
        schema = {}
    try:
        argv = build_argv(tool.command_template or "", schema, args)
    except ToolArgError as e:
        return {"status": "error", "error": str(e)}

    timeout = int(getattr(tool, "timeout_seconds", 60) or 60)

    from app.services.safety_envelope import requires_envelope
    _envelope = requires_envelope(getattr(tool, "action_category", None))
    if _envelope and getattr(tool, "validation_command_template", None):
        from app.services.safety_envelope import run_command
        pre = await run_command(tool.validation_command_template, tool, args)
        if pre.get("exit_code") != 0:
            return {"status": "error", "error": f"pre-action validation failed: {pre.get('stderr')}"}

    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            r = await client.post(
                f"{TOOL_RUNNER_URL}/run",
                json={"argv": argv, "timeout": timeout},
                headers={"X-Runner-Token": RUNNER_TOKEN},
            )
    except Exception as e:
        return {"status": "error", "error": f"tool-runner unreachable: {e}"}

    if r.status_code != 200:
        return {"status": "error", "error": f"tool-runner {r.status_code}: {r.text[:200]}"}
    data = r.json()
    exit_code = data.get("exit_code")
    timed_out = data.get("timed_out", False)
    is_error = bool(timed_out) or (exit_code not in (0, None))
    result = {
        "status": "error" if is_error else "completed",
        "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")),
        "exit_code": exit_code,
        "duration_ms": data.get("duration_ms"),
        "timed_out": timed_out,
        "is_error": is_error,
    }
    if _envelope and getattr(tool, "rollback_command_template", None):
        action_id = str(uuid.uuid4())
        from app.services.safety_envelope import register_rollback
        await register_rollback(action_id, tool, args, ttl_seconds=3600)
        result["action_id"] = action_id
    return result


async def execute_tool(tool, args: Dict[str, Any], user_id: int, *,
                       approved: bool = False,
                       caller_permissions: Optional[set] = None,
                       governance: "GovernanceContext | None" = None,
                       confidence: Optional[float] = None) -> Dict[str, Any]:
    """Validate args, gate on RBAC/approval, run in the tool-runner. JSON-safe result.

    All stages go through ``agent_core.pipeline.run_tool_call`` (INV-28).
    """
    return await run_tool_call(
        tool_name=getattr(tool, "name", None) or "pool_tool",
        arguments=args,
        tool=tool,
        user_id=user_id,
        metadata={
            "approved": approved,
            "caller_permissions": caller_permissions,
            "governance": governance,
            "confidence": confidence,
            "backend": "pool",
        },
        before_tool_call=_pool_before_tool_call,
        execute=_pool_execute,
    )
