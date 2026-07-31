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
