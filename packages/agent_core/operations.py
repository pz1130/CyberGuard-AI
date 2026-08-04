"""Operations ports — tools depend on these, not on host APIs.

Two-tier execution (local sandbox vs governed server-side) is implemented by
injecting different ``Operations`` implementations (DEC-015 / INV-18).

M0a-1: protocols only. No real host I/O here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class ReadOperations(Protocol):
    """Read-only host access (files, env inspection without side effects)."""

    async def read_text(self, path: str, *, max_bytes: int = 1_000_000) -> str:
        """Read a text file. Implementations may refuse paths outside policy roots."""
        ...

    async def list_dir(self, path: str) -> Sequence[str]:
        """List directory entries (names only)."""
        ...


@runtime_checkable
class ExecOperations(Protocol):
    """Structured process execution — never free-form shell strings (INV-35)."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 60,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        """Run ``argv[0]`` with fixed args. Return stdout/stderr/exit_code mapping."""
        ...


@runtime_checkable
class EditOperations(Protocol):
    """Mutating filesystem operations."""

    async def write_text(self, path: str, content: str) -> None:
        ...

    async def delete(self, path: str) -> None:
        ...


@dataclass(frozen=True)
class OperationsBundle:
    """Optional bundle injected into a tool run.

    Capability tiers omit ports they do not grant (e.g. read-only sessions
    set ``exec`` / ``edit`` to None so governed tools cannot run locally).
    """

    read: Optional[ReadOperations] = None
    exec: Optional[ExecOperations] = None
    edit: Optional[EditOperations] = None
