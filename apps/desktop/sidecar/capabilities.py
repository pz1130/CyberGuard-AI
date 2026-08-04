"""Capability tiers → OperationsBundle + dual-knob policy (M1/M2).

readonly: sandboxed Read only — Exec/Edit are None.
full:     sandboxed Read + Edit (workspace/tmp) + allowlisted Exec under Seatbelt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

from agent_core.operations import EditOperations, ExecOperations, OperationsBundle, ReadOperations

from apps.desktop.sidecar.host_ops import (
    ALLOWED_EXEC_BINARIES,
    build_edit_operations,
    build_exec_operations,
    build_read_operations,
)
from apps.desktop.sidecar.paths import data_root, tmp_dir, workspace_dir
from apps.desktop.sidecar.policy import DualKnobPolicy, policy_for_tier
from apps.desktop.sidecar.sandbox import detect_sandbox_impl

Tier = Literal["readonly", "full"]


class MockReadOperations:
    async def read_text(self, path: str, *, max_bytes: int = 1_000_000) -> str:
        return f"[mock-read] {path} (empty — M1 mock)"

    async def list_dir(self, path: str) -> Sequence[str]:
        return ["[mock-dir-entry]"]


class MockExecOperations:
    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 60,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        return {
            "stdout": f"[mock-exec] would run: {' '.join(argv)}",
            "stderr": "",
            "exit_code": 0,
            "mock": True,
        }


class MockEditOperations:
    async def write_text(self, path: str, content: str) -> None:
        return None

    async def delete(self, path: str) -> None:
        return None


@dataclass(frozen=True)
class SessionCapabilities:
    tier: Tier
    operations: OperationsBundle
    policy: DualKnobPolicy
    real_read: bool = False
    real_edit: bool = False
    real_exec: bool = False

    def has_local_exec(self) -> bool:
        return self.operations.exec is not None

    def describe(self) -> dict:
        return {
            "tier": self.tier,
            "has_read": self.operations.read is not None,
            "has_exec": self.operations.exec is not None,
            "has_edit": self.operations.edit is not None,
            "real_read": self.real_read,
            "real_edit": self.real_edit,
            "real_exec": self.real_exec,
            "mock": not (self.real_read or self.real_edit or self.real_exec),
            "sandbox_impl": detect_sandbox_impl(),
            "policy": self.policy.public_status(),
            "allowed_exec_count": len(ALLOWED_EXEC_BINARIES) if self.real_exec else 0,
        }


def capabilities_for_tier(tier: str) -> SessionCapabilities:
    t: Tier = "readonly" if tier == "readonly" else "full"
    root = str(data_root())
    policy = policy_for_tier(
        t,
        workspace_root=str(workspace_dir()),
        managed_tmp=str(tmp_dir()),
    )
    read_ops, real_read = build_read_operations(policy, data_root=root)

    if t == "readonly":
        bundle = OperationsBundle(
            read=read_ops,  # type: ignore[arg-type]
            exec=None,
            edit=None,
        )
        assert bundle.exec is None and bundle.edit is None
        return SessionCapabilities(
            tier="readonly",
            operations=bundle,
            policy=policy,
            real_read=real_read,
            real_edit=False,
            real_exec=False,
        )

    edit_ops, real_edit = build_edit_operations(policy, data_root=root)
    exec_ops, real_exec = build_exec_operations(policy, data_root=root)
    # Fallback to mock exec only if seatbelt path failed entirely
    if not real_exec:
        exec_ops = MockExecOperations()

    bundle = OperationsBundle(
        read=read_ops,  # type: ignore[arg-type]
        exec=exec_ops,  # type: ignore[arg-type]
        edit=edit_ops,  # type: ignore[arg-type]
    )
    return SessionCapabilities(
        tier="full",
        operations=bundle,
        policy=policy,
        real_read=real_read,
        real_edit=real_edit,
        real_exec=real_exec,
    )
