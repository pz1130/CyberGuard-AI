"""Dual-knob policy model (M2): sandbox_mode × approval_policy.

Orthogonal dimensions (desktop design §3.1 / roadmap M2):

- sandbox_mode: what the OS sandbox allows
- approval_policy: when to interrupt for human confirmation

Capability tier (readonly | full) maps to a default dual-knob pair until
the UI exposes knobs explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["untrusted", "on-request", "never"]


@dataclass(frozen=True)
class DualKnobPolicy:
    sandbox_mode: SandboxMode
    approval_policy: ApprovalPolicy
    writable_roots: tuple[str, ...] = ()
    network_access: bool = False
    """When False, Seatbelt denies network syscalls (best-effort)."""

    def public_status(self) -> Dict[str, Any]:
        return {
            "sandbox_mode": self.sandbox_mode,
            "approval_policy": self.approval_policy,
            "writable_roots": list(self.writable_roots),
            "network_access": self.network_access,
        }


def policy_for_tier(
    tier: str,
    *,
    workspace_root: Optional[str] = None,
    managed_tmp: Optional[str] = None,
) -> DualKnobPolicy:
    """Map session tier → dual knobs.

    - readonly → read-only sandbox, on-request approval (no local writes)
    - full     → workspace-write with managed roots only; never danger-full
                 until M2 exit criteria pass and product opts in
    """
    t = "readonly" if str(tier).lower() == "readonly" else "full"
    if t == "readonly":
        return DualKnobPolicy(
            sandbox_mode="read-only",
            approval_policy="on-request",
            writable_roots=(),
            network_access=False,
        )

    roots: List[str] = []
    if workspace_root:
        roots.append(workspace_root)
    if managed_tmp:
        roots.append(managed_tmp)
    return DualKnobPolicy(
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        writable_roots=tuple(roots),
        network_access=False,
    )


def always_readonly_paths(data_root: str) -> tuple[str, ...]:
    """Protective metadata — never writable even under workspace-write (INV).

    Agent may write under ``workspace/`` and ``tmp/`` only. Sessions, audit,
    logs, and config stay read-only at the OS sandbox layer.
    """
    from pathlib import Path

    root = Path(data_root)
    return (
        str(root / "sessions"),
        str(root / "audit"),
        str(root / "logs"),
    )
