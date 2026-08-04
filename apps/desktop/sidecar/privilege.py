"""One-shot privilege escalation retry after sandbox denial (M4).

Flow:
  1. Tool denied by tier/sandbox → create privilege_escalation request
  2. Emit ``privilege_required`` (side channel) so UI can self-approve
  3. Wait (timeout = reject, INV-05)
  4. On approve: retry once with elevated full-tier host ops (still prefer Seatbelt)
  5. Record ``policy_events`` (sandbox_denied → privilege_approved → privilege_retry)

Does **not** permanently mutate session auth_bounds (INV-39); elevation is
per-call and user-approved (``approval_type: self`` in standalone).
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from apps.desktop.sidecar.plan_mode import (
    ACTION_PRIVILEGE_ESCALATION,
    STATUS_APPROVED,
    STATUS_TIMEOUT,
    get_plan_store,
)
from apps.desktop.sidecar.policy_events import append_policy_event

logger = logging.getLogger("cyberguard.desktop.privilege")

SideEmit = Callable[[Dict[str, Any]], Awaitable[None]]


async def elevated_host_call(
    name: str,
    args: Dict[str, Any],
    *,
    hostile_stdout: Callable[[str, str], str],
) -> Dict[str, Any]:
    """Execute one host tool under full-tier policy (workspace-write + allowlisted exec)."""
    from apps.desktop.sidecar.capabilities import capabilities_for_tier

    elev = capabilities_for_tier("full")

    if name in ("host_write_file", "host_delete_file"):
        if elev.operations.edit is None:
            return {
                "status": "error",
                "error": "elevated edit ops unavailable (no seatbelt/workspace-write)",
                "is_error": True,
                "elevated": True,
            }
        path = str(args.get("path") or "")
        if name == "host_write_file":
            content = str(
                args.get("content") if args.get("content") is not None else ""
            )
            await elev.operations.edit.write_text(path, content)
            return {
                "status": "completed",
                "stdout": hostile_stdout(
                    name, f"wrote {path} ({len(content)} chars) [elevated retry]"
                ),
                "is_error": False,
                "sandboxed": elev.real_edit,
                "elevated": True,
                "source_trust": "hostile",
            }
        await elev.operations.edit.delete(path)
        return {
            "status": "completed",
            "stdout": hostile_stdout(name, f"deleted {path} [elevated retry]"),
            "is_error": False,
            "sandboxed": elev.real_edit,
            "elevated": True,
            "source_trust": "hostile",
        }

    if name == "host_run":
        if elev.operations.exec is None:
            return {
                "status": "error",
                "error": "elevated exec ops unavailable",
                "is_error": True,
                "elevated": True,
            }
        raw_argv = args.get("argv")
        if not isinstance(raw_argv, list):
            return {
                "status": "error",
                "error": "argv must be a JSON array of strings",
                "is_error": True,
                "elevated": True,
            }
        timeout = int(args.get("timeout_seconds") or 30)
        cwd = args.get("cwd")
        cwd_s = str(cwd) if cwd else None
        result = await elev.operations.exec.run(
            [str(x) for x in raw_argv],
            timeout_seconds=timeout,
            cwd=cwd_s,
        )
        code = int(result.get("exit_code") or 0)
        out = str(result.get("stdout") or "")
        err = str(result.get("stderr") or "")
        blob = out
        if err:
            blob = (out + ("\n" if out else "") + f"[stderr]\n{err}").strip()
        blob = f"{blob}\n[elevated retry]".strip()
        return {
            "status": "completed" if code == 0 else "error",
            "stdout": hostile_stdout(name, blob),
            "exit_code": code,
            "is_error": code != 0,
            "sandboxed": elev.real_exec,
            "elevated": True,
            "source_trust": "hostile",
        }

    return {
        "status": "error",
        "error": f"privilege retry not supported for tool {name}",
        "is_error": True,
        "elevated": True,
    }


async def request_privilege_and_retry(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    denied_detail: str,
    task: str,
    tier: str,
    run_id: str,
    session_id: Optional[str] = None,
    side_emit: Optional[SideEmit] = None,
    hostile_stdout: Callable[[str, str], str],
) -> Dict[str, Any]:
    """Create privilege request, wait, retry once if approved."""
    store = get_plan_store()
    plan = {
        "summary": (
            f"Privilege escalation for `{tool_name}` after sandbox/tier denial.\n"
            f"Reason: {denied_detail}\n"
            f"Args: {tool_args!r}"
        ),
        "steps": [
            "Review denied action and blast radius",
            f"If approved: one-shot elevated retry of {tool_name}",
            "Record policy_event trail",
        ],
        "blast_radius": {
            "tool": tool_name,
            "args_keys": list((tool_args or {}).keys()),
            "original_tier": tier,
        },
        "risk_level": "high",
        "requires_irreversible": True,
    }
    req = store.create(
        task=task,
        tier=tier,
        plan=plan,
        action_type=ACTION_PRIVILEGE_ESCALATION,
        run_id=run_id,
        session_id=session_id,
        approval_type="self",
        denied_action=tool_name,
        denied_detail=denied_detail,
        tool_name=tool_name,
        tool_args=tool_args,
    )

    append_policy_event(
        "sandbox_denied",
        {
            "tool": tool_name,
            "detail": denied_detail,
            "args_keys": list((tool_args or {}).keys()),
            "tier": tier,
        },
        run_id=run_id,
        session_id=session_id,
        plan_id=req.plan_id,
        approval_type=req.approval_type,
    )

    if side_emit is not None:
        await side_emit(
            {
                "type": "privilege_required",
                "run_id": run_id,
                "plan_id": req.plan_id,
                "action_type": ACTION_PRIVILEGE_ESCALATION,
                "approval_type": req.approval_type,
                "ui_label": req.public_dict()["ui_label"],
                "local_approve_allowed": req.local_approve_allowed(),
                "timeout_seconds": req.timeout_seconds,
                "tool": tool_name,
                "denied_detail": denied_detail,
                "plan": plan,
            }
        )

    decided = await store.wait_decision(req.plan_id)

    if side_emit is not None:
        await side_emit(
            {
                "type": "privilege_decided",
                "run_id": run_id,
                "plan_id": req.plan_id,
                "status": decided.status,
                "reason": decided.reason,
                "approval_type": decided.approval_type,
                "ui_label": decided.public_dict().get("ui_label"),
            }
        )

    if decided.status != STATUS_APPROVED:
        reason = decided.reason or decided.status
        if decided.status == STATUS_TIMEOUT:
            reason = "timeout_rejected"
        append_policy_event(
            "privilege_rejected",
            {"tool": tool_name, "status": decided.status, "reason": reason},
            run_id=run_id,
            session_id=session_id,
            plan_id=req.plan_id,
            approval_type=decided.approval_type,
        )
        return {
            "status": "error",
            "error": (
                f"sandbox denied {tool_name}; privilege {decided.status}: {reason}"
            ),
            "is_error": True,
            "can_escalate": False,
            "privilege_plan_id": req.plan_id,
            "privilege_status": decided.status,
        }

    append_policy_event(
        "privilege_approved",
        {
            "tool": tool_name,
            "approval_type": decided.approval_type,
            "elevated_to": "full",
        },
        run_id=run_id,
        session_id=session_id,
        plan_id=req.plan_id,
        approval_type=decided.approval_type,
    )

    try:
        result = await elevated_host_call(
            tool_name, tool_args or {}, hostile_stdout=hostile_stdout
        )
    except Exception as exc:  # noqa: BLE001
        append_policy_event(
            "privilege_retry_failed",
            {"tool": tool_name, "error": f"{type(exc).__name__}: {exc}"},
            run_id=run_id,
            session_id=session_id,
            plan_id=req.plan_id,
            approval_type=decided.approval_type,
        )
        return {
            "status": "error",
            "error": f"elevated retry failed: {exc}",
            "is_error": True,
            "elevated": True,
            "privilege_plan_id": req.plan_id,
        }

    req.retry_count = 1
    append_policy_event(
        "privilege_retry",
        {
            "tool": tool_name,
            "success": not bool(result.get("is_error")),
            "sandboxed": result.get("sandboxed"),
            "elevated": True,
        },
        run_id=run_id,
        session_id=session_id,
        plan_id=req.plan_id,
        approval_type=decided.approval_type,
    )

    if side_emit is not None:
        await side_emit(
            {
                "type": "policy_event",
                "run_id": run_id,
                "plan_id": req.plan_id,
                "policy_event_type": "privilege_retry",
                "tool": tool_name,
                "success": not bool(result.get("is_error")),
                "approval_type": decided.approval_type,
            }
        )

    result = dict(result)
    result["privilege_plan_id"] = req.plan_id
    result["privilege_status"] = STATUS_APPROVED
    return result
