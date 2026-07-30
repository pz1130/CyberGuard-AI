"""Capability tiers → OperationsBundle (M1).

readonly: ReadOperations only — ExecOperations and EditOperations are None
           (type-level guarantee: no local exec port exists on the instance).
full:     mock Read + Exec + Edit (still fake — no real host I/O in M1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

from agent_core.operations import EditOperations, ExecOperations, OperationsBundle, ReadOperations

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

    def has_local_exec(self) -> bool:
        return self.operations.exec is not None

    def describe(self) -> dict:
        return {
            "tier": self.tier,
            "has_read": self.operations.read is not None,
            "has_exec": self.operations.exec is not None,
            "has_edit": self.operations.edit is not None,
            "mock": True,
        }


def capabilities_for_tier(tier: str) -> SessionCapabilities:
    t: Tier = "readonly" if tier == "readonly" else "full"
    if t == "readonly":
        # INV / M1: readonly instances must not carry ExecOperations
        bundle = OperationsBundle(
            read=MockReadOperations(),  # type: ignore[arg-type]
            exec=None,
            edit=None,
        )
        assert bundle.exec is None and bundle.edit is None
        return SessionCapabilities(tier="readonly", operations=bundle)

    bundle = OperationsBundle(
        read=MockReadOperations(),  # type: ignore[arg-type]
        exec=MockExecOperations(),  # type: ignore[arg-type]
        edit=MockEditOperations(),  # type: ignore[arg-type]
    )
    return SessionCapabilities(tier="full", operations=bundle)
