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
    # INV: .git stays read-only even inside a writable root
    if ".git" in path.parts:
        raise HostOpsError("path under .git is protected (read-only)")
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


# INV-35: structured argv only — absolute binary allowlist, no free-form shell.
ALLOWED_EXEC_BINARIES = frozenset(
    {
        "/bin/ls",
        "/bin/cat",
        "/bin/echo",
        "/bin/pwd",
        "/bin/mkdir",
        "/bin/rm",
        "/bin/cp",
        "/bin/mv",
        "/usr/bin/head",
        "/usr/bin/tail",
        "/usr/bin/wc",
        "/usr/bin/file",
        "/usr/bin/stat",
        "/usr/bin/grep",
        "/usr/bin/find",
        "/usr/bin/sort",
        "/usr/bin/uniq",
        "/usr/bin/diff",
        "/usr/bin/tee",
        "/usr/bin/uname",
        "/usr/bin/which",
        "/usr/bin/md5",
        "/sbin/md5",
        "/usr/bin/shasum",
        "/usr/bin/basename",
        "/usr/bin/dirname",
    }
)

_MAX_ARGV = 32
_MAX_ARG_LEN = 4096
_MAX_TIMEOUT = 60


def _validate_exec_argv(argv: Sequence[str]) -> list[str]:
    if not argv:
        raise HostOpsError("argv required")
    if len(argv) > _MAX_ARGV:
        raise HostOpsError(f"too many argv entries (max {_MAX_ARGV})")
    out: list[str] = []
    for i, a in enumerate(argv):
        if not isinstance(a, str):
            raise HostOpsError("argv entries must be strings")
        if len(a) > _MAX_ARG_LEN:
            raise HostOpsError(f"argv[{i}] too long")
        if "\x00" in a:
            raise HostOpsError("argv must not contain NUL")
        out.append(a)
    binary = out[0]
    if not binary.startswith("/"):
        raise HostOpsError("argv[0] must be an absolute path")
    # Resolve symlinks for allowlist check
    try:
        resolved = str(Path(binary).resolve(strict=True))
    except OSError as exc:
        raise HostOpsError(f"binary not found: {binary}") from exc
    if binary not in ALLOWED_EXEC_BINARIES and resolved not in ALLOWED_EXEC_BINARIES:
        raise HostOpsError(
            f"binary not on allowlist: {binary} (resolved {resolved})"
        )
    # Prefer the path that exists on disk for exec
    out[0] = resolved if Path(resolved).is_file() else binary
    # Never allow shell -c style via sh/bash (not on list). Extra: block python -c.
    return out


class SandboxedExecOperations:
    """ExecOperations: allowlisted argv only, always under Seatbelt."""

    def __init__(
        self,
        policy: DualKnobPolicy,
        *,
        data_root: str,
        profile_dir: Optional[Path] = None,
    ) -> None:
        if detect_sandbox_impl() != "seatbelt":
            raise HostOpsError("SandboxedExecOperations requires seatbelt")
        self.policy = policy
        self.data_root = data_root
        self.readonly_paths = always_readonly_paths(data_root)
        self.profile_dir = profile_dir
        # Default cwd: first writable root (workspace) when available
        roots = list(policy.writable_roots)
        self.default_cwd = roots[0] if roots else None

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 60,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        clean = _validate_exec_argv(argv)
        timeout = max(1, min(int(timeout_seconds or 30), _MAX_TIMEOUT))
        work_cwd = cwd or self.default_cwd
        if work_cwd:
            cwd_path = Path(work_cwd).expanduser()
            if not cwd_path.is_absolute():
                raise HostOpsError("cwd must be absolute")
            if self.policy.writable_roots and not _under_any_root(
                cwd_path, self.policy.writable_roots
            ):
                raise HostOpsError(
                    f"cwd outside writable_roots: {cwd_path}"
                )
            cwd_path.mkdir(parents=True, exist_ok=True)
            work_cwd = str(cwd_path.resolve())
        # Minimal env — do not inherit secrets from parent
        safe_env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": os.environ.get("HOME", "/var/empty"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "TMPDIR": self.default_cwd or "/tmp",
        }
        if env:
            # Only allow a few non-secret overrides
            for k in ("LANG", "LC_ALL", "TZ"):
                if k in env and isinstance(env[k], str):
                    safe_env[k] = env[k]

        result = await asyncio.to_thread(
            run_sandboxed,
            clean,
            self.policy,
            readonly_paths=self.readonly_paths,
            cwd=work_cwd,
            env=safe_env,
            timeout_seconds=timeout,
            profile_dir=self.profile_dir,
        )
        return {
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
            "exit_code": int(result.get("exit_code") or 0),
            "sandboxed": True,
            "argv": clean,
            "cwd": work_cwd,
            "mock": False,
        }


class DeniedExecOperations:
    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 60,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        raise HostOpsError(
            "host exec denied: requires full tier + seatbelt + allowlisted argv"
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


def build_exec_operations(
    policy: DualKnobPolicy,
    *,
    data_root: str,
) -> tuple[Any, bool]:
    """Return (exec_ops, is_real) for full tier with seatbelt."""
    if detect_sandbox_impl() != "seatbelt":
        return DeniedExecOperations(), False
    # Exec is available on full (workspace-write) so cwd can default to workspace
    if policy.sandbox_mode not in ("workspace-write", "read-only"):
        return DeniedExecOperations(), False
    try:
        return (
            SandboxedExecOperations(policy, data_root=data_root),
            True,
        )
    except (HostOpsError, SeatbeltError):
        return DeniedExecOperations(), False
