"""Executable Tool pool — validate args, build an injection-safe argv, and run
it in the isolated tool-runner container. See:
  docs/superpowers/specs/2026-05-29-tool-pool-executable-design.md
"""
import json
import os
import shlex
import uuid
from typing import Any, Dict, List, Optional

import httpx


TOOL_RUNNER_URL = os.environ.get("TOOL_RUNNER_URL", "http://tool-runner:9000")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
OUTPUT_MAX_CHARS = 8000  # mirror internal_agent.TOOL_RESULT_MAX_CHARS


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
    props = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []

    for k in args:
        if k not in props:
            raise ToolArgError(f"unknown argument: {k!r}")
    for k in required:
        if k not in args:
            raise ToolArgError(f"missing required argument: {k!r}")

    for k, v in args.items():
        prop = props.get(k, {})
        enum = prop.get("enum")
        if enum is not None and v not in enum:
            raise ToolArgError(f"argument {k!r}={v!r} not in enum {enum}")
        t = prop.get("type")
        if t == "integer":
            ok = (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, str) and v.lstrip("-").isdigit())
            if not ok:
                raise ToolArgError(f"argument {k!r} must be an integer, got {v!r}")
        elif t == "number":
            ok = (isinstance(v, (int, float)) and not isinstance(v, bool))
            if not ok and isinstance(v, str):
                try: float(v); ok = True
                except ValueError: ok = False
            if not ok:
                raise ToolArgError(f"argument {k!r} must be a number, got {v!r}")

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


def _truncate(text: str) -> str:
    if text and len(text) > OUTPUT_MAX_CHARS:
        return text[:OUTPUT_MAX_CHARS] + f"\n…[truncated {len(text) - OUTPUT_MAX_CHARS} chars]"
    return text or ""


async def _create_approval(tool, args: Dict[str, Any], user_id: int) -> None:
    from app.services.approval_service import ApprovalService
    await ApprovalService().create_request(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        action_type="tool.execute",
        action_description=f"Execute tool {getattr(tool, 'name', '?')}",
        payload={"tool": getattr(tool, "name", None), "args": args},
        risk_level="high",
    )


async def execute_tool(tool, args: Dict[str, Any], user_id: int, *,
                       approved: bool = False,
                       caller_permissions: Optional[set] = None,
                       governance: "GovernanceContext | None" = None,
                       confidence: Optional[float] = None) -> Dict[str, Any]:
    """Validate args, gate on RBAC/approval, run in the tool-runner. JSON-safe result."""
    # Kill switch — hardest gate, checked before anything else (NDB Std §Kill Switch).
    from app.services.kill_switch import is_halted
    if await is_halted(agent_id=getattr(tool, "agent_id", None)):
        from app.core.audit import record_action
        await record_action(user_id=user_id, agent_name=getattr(tool, "name", None),
                            action="EMERGENCY_HALT", action_category=getattr(tool, "action_category", None),
                            input_data={"tool": getattr(tool, "name", None), "args": args},
                            output_data={"blocked": True})
        return {"status": "halted", "error": "kill switch engaged"}

    # RBAC: only enforced when caller_permissions is provided (API path). The
    # internal-agent path passes None — assignment to the agent is the authorization.
    req = getattr(tool, "required_permission", None)
    if req and caller_permissions is not None and req not in caller_permissions:
        return {"status": "error", "error": f"missing required permission: {req}"}

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
            return {"status": "denied", "error": verdict.reason}
        if verdict.decision is Decision.NEEDS_APPROVAL and not approved:
            await _create_approval(tool, args, user_id)
            return {"status": "needs_approval", "error": verdict.reason}

    # Approval gate for high-permission tools.
    if getattr(tool, "permission_level", "medium") == "high" and not approved:
        await _create_approval(tool, args, user_id)
        return {"status": "needs_approval",
                "error": "High-permission tool requires approval"}

    try:
        schema = json.loads(tool.input_schema_json) if tool.input_schema_json else {}
    except json.JSONDecodeError:
        schema = {}
    try:
        argv = build_argv(tool.command_template or "", schema, args)
    except ToolArgError as e:
        return {"status": "error", "error": str(e)}

    timeout = int(getattr(tool, "timeout_seconds", 60) or 60)
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
    return {
        "status": "completed",
        "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")),
        "exit_code": data.get("exit_code"),
        "duration_ms": data.get("duration_ms"),
        "timed_out": data.get("timed_out", False),
    }
