"""Host Operations behind OS sandbox (M2).

Real filesystem I/O for agent tools MUST go through Seatbelt (or be denied).
Unsandboxed host I/O from the sidecar process is intentionally not exposed.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from apps.desktop.sidecar.policy import DualKnobPolicy, always_readonly_paths
from apps.desktop.sidecar.sandbox import SeatbeltError, detect_sandbox_impl, run_sandboxed
from apps.desktop.sidecar.sandbox.detect import SANDBOX_EXEC

# Never hand these to the model via host tools (credential surface).
_BLOCKED_NAME_SUFFIXES = (
    "provider.json",
    ".env",
    ".pem",
    ".key",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "secret",
)


class HostOpsError(RuntimeError):
    pass


def _is_blocked_path(path: Path) -> bool:
    name = path.name.lower()
    full = str(path).lower()
    for s in _BLOCKED_NAME_SUFFIXES:
        if name == s or name.endswith(s) or full.endswith("/" + s):
            return True
        if s in ("secret",) and s in name:
            return True
    return False


def _resolve_path(path: str) -> Path:
    if not path or not str(path).strip():
        raise HostOpsError("path required")
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise HostOpsError("path must be absolute")
    try:
        resolved = p.resolve(strict=False)
    except OSError as exc:
        raise HostOpsError(f"invalid path: {exc}") from exc
    if _is_blocked_path(resolved) or _is_blocked_path(p):
        raise HostOpsError("path blocked (credential/sensitive file)")
    return resolved


class SandboxedReadOperations:
    """ReadOperations that only performs I/O inside sandbox-exec children."""

    def __init__(
        self,
        policy: DualKnobPolicy,
        *,
        data_root: str,
        profile_dir: Optional[Path] = None,
    ) -> None:
        if detect_sandbox_impl() != "seatbelt":
            raise HostOpsError("SandboxedReadOperations requires seatbelt")
        if not Path(SANDBOX_EXEC).is_file():
            raise HostOpsError(f"missing {SANDBOX_EXEC}")
        self.policy = policy
        self.readonly_paths = always_readonly_paths(data_root)
        self.profile_dir = profile_dir

    async def read_text(self, path: str, *, max_bytes: int = 1_000_000) -> str:
        target = _resolve_path(path)
        if max_bytes <= 0:
            max_bytes = 1_000_000
        max_bytes = min(int(max_bytes), 5_000_000)
        # Prefer /usr/bin/head (macOS may not ship /bin/head)
        head_bin = "/usr/bin/head" if Path("/usr/bin/head").is_file() else "/bin/cat"
        if head_bin.endswith("head"):
            argv = [head_bin, "-c", str(max_bytes), str(target)]
        else:
            argv = [head_bin, str(target)]
        result = await asyncio.to_thread(
            run_sandboxed,
            argv,
            self.policy,
            readonly_paths=self.readonly_paths,
            timeout_seconds=30,
            profile_dir=self.profile_dir,
        )
        if int(result.get("exit_code") or 0) != 0:
            err = (result.get("stderr") or result.get("stdout") or "read failed").strip()
            raise HostOpsError(f"sandboxed read failed: {err[:400]}")
        text = str(result.get("stdout") or "")
        if head_bin.endswith("cat") and len(text.encode("utf-8", errors="replace")) > max_bytes:
            # best-effort truncate for cat fallback
            raw = text.encode("utf-8", errors="replace")[:max_bytes]
            text = raw.decode("utf-8", errors="replace")
        # head may not set error on missing file on all systems — double-check
        if not text and not target.is_file():
            raise HostOpsError(f"not a file: {target}")
        return text

    async def list_dir(self, path: str) -> Sequence[str]:
        target = _resolve_path(path)
        result = await asyncio.to_thread(
            run_sandboxed,
            ["/bin/ls", "-1A", str(target)],
            self.policy,
            readonly_paths=self.readonly_paths,
            timeout_seconds=30,
            profile_dir=self.profile_dir,
        )
        if int(result.get("exit_code") or 0) != 0:
            err = (result.get("stderr") or result.get("stdout") or "list failed").strip()
            raise HostOpsError(f"sandboxed list_dir failed: {err[:400]}")
        out = str(result.get("stdout") or "")
        names = [ln for ln in out.splitlines() if ln]
        return names


class DeniedReadOperations:
    """Used when sandbox_impl is none — real host I/O is not available."""

    async def read_text(self, path: str, *, max_bytes: int = 1_000_000) -> str:
        raise HostOpsError(
            "host read denied: no OS sandbox (sandbox_impl=none). "
            "Real host tools stay disabled (INV-16)."
        )

    async def list_dir(self, path: str) -> Sequence[str]:
        raise HostOpsError(
            "host list_dir denied: no OS sandbox (sandbox_impl=none)."
        )


def _under_any_root(path: Path, roots: Sequence[str]) -> bool:
    resolved = path.resolve(strict=False)
    for root in roots:
        if not root:
            continue
        try:
            resolved.relative_to(Path(root).resolve(strict=False))
            return True
        except ValueError:
            continue
    return False


def _assert_writable_target(
    path: Path,
    policy: DualKnobPolicy,
    *,
    data_root: str,
) -> None:
    if policy.sandbox_mode != "workspace-write":
        raise HostOpsError(
            f"writes require workspace-write sandbox (got {policy.sandbox_mode})"
        )
    if not policy.writable_roots:
        raise HostOpsError("no writable_roots configured")
    if not _under_any_root(path, policy.writable_roots):
        raise HostOpsError(
            f"path outside writable_roots: {path} "
            f"(allowed: {list(policy.writable_roots)})"
        )
    for protected in always_readonly_paths(data_root):
        if _under_any_root(path, (protected,)):
            raise HostOpsError(f"path is protective metadata (read-only): {path}")


class SandboxedEditOperations:
    """EditOperations that only mutate files inside workspace-write roots."""

    def __init__(
        self,
        policy: DualKnobPolicy,
        *,
        data_root: str,
        profile_dir: Optional[Path] = None,
    ) -> None:
        if detect_sandbox_impl() != "seatbelt":
            raise HostOpsError("SandboxedEditOperations requires seatbelt")
        if policy.sandbox_mode != "workspace-write":
            raise HostOpsError("SandboxedEditOperations requires workspace-write policy")
        self.policy = policy
        self.data_root = data_root
        self.readonly_paths = always_readonly_paths(data_root)
        self.profile_dir = profile_dir

    async def write_text(self, path: str, content: str) -> None:
        target = _resolve_path(path)
        _assert_writable_target(target, self.policy, data_root=self.data_root)
        # Ensure parent exists outside sandbox (mkdir under writable root only)
        parent = target.parent
        if not _under_any_root(parent, self.policy.writable_roots):
            raise HostOpsError(f"parent not under writable_roots: {parent}")
        parent.mkdir(parents=True, exist_ok=True)
        # Write via sandboxed tee reading stdin (never write from sidecar process)
        result = await asyncio.to_thread(
            run_sandboxed,
            ["/usr/bin/tee", str(target)],
            self.policy,
            readonly_paths=self.readonly_paths,
            timeout_seconds=30,
            profile_dir=self.profile_dir,
            input_text=content if content is not None else "",
        )
        if int(result.get("exit_code") or 0) != 0:
            err = (result.get("stderr") or result.get("stdout") or "write failed").strip()
            raise HostOpsError(f"sandboxed write failed: {err[:400]}")

    async def delete(self, path: str) -> None:
        target = _resolve_path(path)
        _assert_writable_target(target, self.policy, data_root=self.data_root)
        if not target.exists():
            return
        result = await asyncio.to_thread(
            run_sandboxed,
            ["/bin/rm", "-f", str(target)],
            self.policy,
            readonly_paths=self.readonly_paths,
            timeout_seconds=30,
            profile_dir=self.profile_dir,
        )
        if int(result.get("exit_code") or 0) != 0:
            err = (result.get("stderr") or result.get("stdout") or "delete failed").strip()
            raise HostOpsError(f"sandboxed delete failed: {err[:400]}")


class DeniedEditOperations:
    async def write_text(self, path: str, content: str) -> None:
        raise HostOpsError(
            "host write denied: requires full tier + seatbelt workspace-write"
        )

    async def delete(self, path: str) -> None:
        raise HostOpsError(
            "host delete denied: requires full tier + seatbelt workspace-write"
        )


def build_read_operations(
    policy: DualKnobPolicy,
    *,
    data_root: str,
) -> tuple[Any, bool]:
    """Return (read_ops, is_real).

    is_real True → Seatbelt-backed. False → denied (no unsandboxed I/O).
    """
    impl = detect_sandbox_impl()
    if impl == "seatbelt":
        try:
            return (
                SandboxedReadOperations(policy, data_root=data_root),
                True,
            )
        except (HostOpsError, SeatbeltError):
            return DeniedReadOperations(), False
    # No seatbelt: do not expose unsandboxed real I/O
    return DeniedReadOperations(), False


def build_edit_operations(
    policy: DualKnobPolicy,
    *,
    data_root: str,
) -> tuple[Any, bool]:
    """Return (edit_ops, is_real) for workspace-write only."""
    if policy.sandbox_mode != "workspace-write":
        return DeniedEditOperations(), False
    if detect_sandbox_impl() != "seatbelt":
        return DeniedEditOperations(), False
    try:
        return (
            SandboxedEditOperations(policy, data_root=data_root),
            True,
        )
    except (HostOpsError, SeatbeltError):
        return DeniedEditOperations(), False
