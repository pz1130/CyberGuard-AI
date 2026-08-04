"""M4 Plan Mode + local self-approval (standalone).

INV-05: approval timeout = **reject** (never default-approve).
INV-06 / INV-38: standalone approvals are ``approval_type: self`` and must be
labelled "自批准" — never conflated with segregation-of-duties.
INV-19: irreversible tools must not run until a plan is approved.

Connected runtime (future): node UI must not show approve buttons for SoD
matters; only local-confirm path is implemented here.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("cyberguard.desktop.plan_mode")

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"

ACTION_EXECUTION_PLAN = "execution_plan"
ACTION_PRIVILEGE_ESCALATION = "privilege_escalation"

# Tools considered irreversible / side-effecting (INV-19)
IRREVERSIBLE_TOOL_PREFIXES = (
    "host_write",
    "host_delete",
    "host_run",
    "mock_scan",
)

RISK_KEYWORDS = (
    "scan",
    "nmap",
    "block",
    "ban",
    "kill",
    "terminate",
    "delete",
    "wipe",
    "isolate",
    "contain",
    "exploit",
    "ransomware",
    "封禁",
    "隔离",
    "删除",
    "扫描",
    "终止",
)


def default_timeout_seconds() -> float:
    try:
        return float(os.environ.get("CYBERGUARD_PLAN_TIMEOUT_SECONDS") or "300")
    except ValueError:
        return 300.0


def auto_approve_enabled() -> bool:
    v = (os.environ.get("CYBERGUARD_PLAN_AUTO_APPROVE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def runtime_mode() -> str:
    """standalone | connected — connected never shows local SoD approve (INV-06)."""
    m = (os.environ.get("CYBERGUARD_RUNTIME") or "standalone").strip().lower()
    return "connected" if m == "connected" else "standalone"


def _task_has_risk_keyword(task: str) -> bool:
    """Word-boundary match so ``skill`` does not trigger ``kill``."""
    import re

    task_l = (task or "").lower()
    if not task_l:
        return False
    for k in RISK_KEYWORDS:
        # ASCII word boundaries; CJK keywords match as plain substring
        if re.search(r"[a-z]", k):
            if re.search(rf"\b{re.escape(k)}\b", task_l):
                return True
        elif k in task_l:
            return True
    return False


def plan_required(
    *,
    tier: str,
    task: str,
    tool_names: Sequence[str],
) -> bool:
    """Whether execution must wait for an approved plan."""
    force = (os.environ.get("CYBERGUARD_REQUIRE_PLAN") or "").strip().lower()
    if force in ("1", "true", "yes", "always"):
        return True
    if force in ("0", "false", "no", "never"):
        return False
    names = [str(n or "") for n in tool_names]
    if any(
        any(n == p or n.startswith(p + "_") or n.startswith(p) for p in IRREVERSIBLE_TOOL_PREFIXES)
        for n in names
    ):
        return True
    if str(tier).lower() == "full":
        # Full tier can host_run/write when seatbelt live — gate by default
        return True
    if _task_has_risk_keyword(task):
        return True
    return False


def draft_plan(
    *,
    task: str,
    tier: str,
    tool_names: Sequence[str],
    skills: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Heuristic structured plan (no extra LLM required for offline)."""
    tools = list(tool_names or [])
    irreversible = [
        t
        for t in tools
        if any(t == p or t.startswith(p) for p in IRREVERSIBLE_TOOL_PREFIXES)
    ]
    read_only = [t for t in tools if t not in irreversible and t != "load_skill"]
    steps: List[str] = [
        "Clarify objective and constraints from the user task.",
        "Load relevant SOP via load_skill if listed skills apply.",
    ]
    if any(t.startswith("mcp__") for t in tools):
        steps.append("Query MCP data sources (read-only) for evidence.")
    if "host_read_file" in tools or "host_list_dir" in tools:
        steps.append("Read local files under sandbox when paths are known.")
    if irreversible:
        steps.append(
            f"Execute side-effecting tools only as approved: {', '.join(irreversible)}."
        )
    steps.append("Produce a Markdown report with sources and uncertainties.")

    blast = {
        "hosts": "unknown until inventory",
        "networks": "unknown",
        "data_classes": ["investigation notes", "tool outputs"],
        "irreversible_tools": irreversible,
    }
    summary = (
        f"Tier={tier}. Objective: {(task or '')[:500]}\n"
        f"Steps:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
    )
    return {
        "summary": summary,
        "steps": steps,
        "blast_radius": blast,
        "tools_planned": tools,
        "skills_planned": list(skills or []),
        "risk_level": "high" if irreversible else ("medium" if tier == "full" else "low"),
        "requires_irreversible": bool(irreversible),
    }


@dataclass
class ApprovalRequest:
    plan_id: str
    action_type: str
    task: str
    tier: str
    plan: Dict[str, Any]
    status: str = STATUS_PENDING
    approval_type: str = "self"  # self | segregation (segregation never local-approved)
    created_at: float = field(default_factory=time.time)
    decided_at: Optional[float] = None
    timeout_seconds: float = 300.0
    revised_plan: Optional[str] = None
    reason: str = ""
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    runtime: str = "standalone"
    # privilege escalation fields
    denied_action: Optional[str] = None
    denied_detail: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    # wait plumbing
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "action_type": self.action_type,
            "task": self.task,
            "tier": self.tier,
            "plan": self.plan,
            "status": self.status,
            "approval_type": self.approval_type,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "timeout_seconds": self.timeout_seconds,
            "revised_plan": self.revised_plan,
            "reason": self.reason,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "runtime": self.runtime,
            "denied_action": self.denied_action,
            "denied_detail": self.denied_detail,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args or {},
            "retry_count": self.retry_count,
            # UI hint: when connected + segregation, no local approve button
            "local_approve_allowed": self.local_approve_allowed(),
            "ui_label": "自批准" if self.approval_type == "self" else "职责分离审批",
        }

    def local_approve_allowed(self) -> bool:
        if self.runtime == "connected" and self.approval_type == "segregation":
            return False
        return self.status == STATUS_PENDING


class PlanApprovalStore:
    """In-process pending plans (one desktop user). Thread-safe registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Dict[str, ApprovalRequest] = {}

    def create(
        self,
        *,
        task: str,
        tier: str,
        plan: Dict[str, Any],
        action_type: str = ACTION_EXECUTION_PLAN,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        approval_type: str = "self",
        denied_action: Optional[str] = None,
        denied_detail: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        pid = str(uuid.uuid4())
        rt = runtime_mode()
        # Connected SoD never uses local self for privilege — still label honestly
        at = approval_type
        if rt == "connected" and action_type == ACTION_PRIVILEGE_ESCALATION:
            at = "segregation"
        req = ApprovalRequest(
            plan_id=pid,
            action_type=action_type,
            task=task,
            tier=tier,
            plan=plan,
            approval_type=at,
            timeout_seconds=(
                float(timeout_seconds)
                if timeout_seconds is not None
                else default_timeout_seconds()
            ),
            run_id=run_id,
            session_id=session_id,
            runtime=rt,
            denied_action=denied_action,
            denied_detail=denied_detail,
            tool_name=tool_name,
            tool_args=dict(tool_args or {}),
        )
        with self._lock:
            self._items[pid] = req
        return req

    def get(self, plan_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._items.get(plan_id)

    def list(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            items = sorted(
                self._items.values(), key=lambda r: r.created_at, reverse=True
            )
        return [r.public_dict() for r in items[:limit]]

    def decide(
        self,
        plan_id: str,
        *,
        approve: bool,
        revised_plan: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        req = self.get(plan_id)
        if req is None:
            return {"ok": False, "error": "unknown_plan_id"}
        if not req.local_approve_allowed() and approve:
            return {
                "ok": False,
                "error": "local_approve_forbidden",
                "message": (
                    "Connected segregation-of-duties approvals cannot be approved "
                    "on the node UI (INV-06)."
                ),
                "plan": req.public_dict(),
            }
        if req.status != STATUS_PENDING:
            return {"ok": False, "error": "not_pending", "plan": req.public_dict()}

        if approve:
            req.status = STATUS_APPROVED
            if revised_plan is not None:
                req.revised_plan = revised_plan
        else:
            req.status = STATUS_REJECTED
            req.reason = reason or "rejected_by_user"
        req.decided_at = time.time()
        req._event.set()
        self._audit(req)
        return {"ok": True, "plan": req.public_dict()}

    def _audit(self, req: ApprovalRequest) -> None:
        try:
            from apps.desktop.sidecar.audit_chain import append_event

            append_event(
                "plan_decision" if req.action_type == ACTION_EXECUTION_PLAN else "privilege_decision",
                {
                    "plan_id": req.plan_id,
                    "action_type": req.action_type,
                    "status": req.status,
                    "approval_type": req.approval_type,
                    "risk_level": (req.plan or {}).get("risk_level"),
                    "revised": bool(req.revised_plan),
                    "reason": req.reason,
                    "denied_action": req.denied_action,
                },
                approval_type=req.approval_type,
                session_id=req.session_id,
                run_id=req.run_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("plan audit failed", exc_info=True)

    async def wait_decision(self, plan_id: str) -> ApprovalRequest:
        """Wait until decided or timeout → STATUS_TIMEOUT (reject)."""
        req = self.get(plan_id)
        if req is None:
            raise KeyError(plan_id)
        if auto_approve_enabled() and req.local_approve_allowed():
            # Dev/test only — still labels approval_type self
            self.decide(plan_id, approve=True, reason="auto_approve")
            return req  # type: ignore[return-value]

        try:
            await asyncio.wait_for(req._event.wait(), timeout=req.timeout_seconds)
        except asyncio.TimeoutError:
            if req.status == STATUS_PENDING:
                req.status = STATUS_TIMEOUT
                req.reason = "timeout_rejected"  # INV-05
                req.decided_at = time.time()
                req._event.set()
                self._audit(req)
        return req

    def cancel_run(self, run_id: str) -> int:
        n = 0
        with self._lock:
            for req in self._items.values():
                if req.run_id == run_id and req.status == STATUS_PENDING:
                    req.status = STATUS_CANCELLED
                    req.reason = "run_aborted"
                    req.decided_at = time.time()
                    req._event.set()
                    n += 1
        return n


_STORE: Optional[PlanApprovalStore] = None


def get_plan_store() -> PlanApprovalStore:
    global _STORE
    if _STORE is None:
        _STORE = PlanApprovalStore()
    return _STORE


def reset_plan_store_for_tests() -> None:
    global _STORE
    _STORE = PlanApprovalStore()
