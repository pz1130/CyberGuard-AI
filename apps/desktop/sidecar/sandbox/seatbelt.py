"""macOS Seatbelt helpers (M2).

Hard requirements from design:
- Always invoke ``/usr/bin/sandbox-exec`` by absolute path (never PATH lookup)
- read-only: no network, no file writes (except required device nodes)
- workspace-write: only listed writable_roots; protective paths stay read-only
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

from apps.desktop.sidecar.policy import DualKnobPolicy
from apps.desktop.sidecar.sandbox.detect import SANDBOX_EXEC


def _sb_path(p: str) -> str:
    return p.replace("\\", "\\\\").replace('"', '\\"')


class SeatbeltError(RuntimeError):
    pass


def build_profile(
    policy: DualKnobPolicy,
    *,
    readonly_paths: Sequence[str] = (),
) -> str:
    """Return a Seatbelt (sbpl) profile string for *policy*.

    Strategy: start open enough to run system binaries, then **deny all
    file-write*** and only re-allow explicit roots. Never blanket-allow
    ``/var/folders`` (pytest/tmp live there).
    """
    if policy.sandbox_mode == "danger-full-access":
        raise SeatbeltError(
            "danger-full-access profiles are not generated until M2 exit criteria pass"
        )
    if policy.sandbox_mode not in ("read-only", "workspace-write"):
        raise SeatbeltError(f"unknown sandbox_mode: {policy.sandbox_mode}")

    lines: List[str] = [
        "(version 1)",
        # Permit process/runtime, then lock down writes explicitly.
        "(allow default)",
        "(deny file-write*)",
        '(allow file-write* (literal "/dev/null"))',
        '(allow file-write* (literal "/dev/tty"))',
        '(allow file-write-data (literal "/dev/dtracehelper"))',
        '(allow file-ioctl (literal "/dev/dtracehelper"))',
    ]

    if policy.sandbox_mode == "read-only":
        lines.append("(deny network*)")
    else:
        # workspace-write: only listed roots
        for root in policy.writable_roots:
            if not root:
                continue
            for candidate in (os.path.realpath(root), os.path.abspath(root)):
                rp = _sb_path(candidate)
                lines.append(f'(allow file-write* (subpath "{rp}"))')
        if not policy.network_access:
            lines.append("(deny network*)")
        # Protective paths: deny after allows so they stay read-only even
        # when nested under a writable root (Seatbelt: last matching rule).
        for p in readonly_paths:
            if not p:
                continue
            for candidate in (os.path.realpath(p), os.path.abspath(p)):
                rp = _sb_path(candidate)
                lines.append(f'(deny file-write* (subpath "{rp}"))')

    return "\n".join(lines) + "\n"


def write_profile(
    policy: DualKnobPolicy,
    *,
    readonly_paths: Sequence[str] = (),
    directory: Optional[Path] = None,
) -> Path:
    text = build_profile(policy, readonly_paths=readonly_paths)
    if directory is None:
        directory = Path(tempfile.mkdtemp(prefix="cg-sb-"))
    else:
        directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{policy.sandbox_mode.replace('/', '-')}.sb"
    path.write_text(text, encoding="utf-8")
    return path


def run_sandboxed(
    argv: Sequence[str],
    policy: DualKnobPolicy,
    *,
    readonly_paths: Sequence[str] = (),
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout_seconds: int = 30,
    profile_dir: Optional[Path] = None,
    input_text: Optional[str] = None,
) -> Mapping[str, object]:
    """Run argv under Seatbelt. Returns stdout/stderr/exit_code/sandboxed."""
    if not Path(SANDBOX_EXEC).is_file():
        raise SeatbeltError(f"sandbox-exec missing at {SANDBOX_EXEC}")
    if not argv:
        raise SeatbeltError("argv required")

    profile = write_profile(
        policy, readonly_paths=readonly_paths, directory=profile_dir
    )
    cmd = [SANDBOX_EXEC, "-f", str(profile), *list(argv)]
    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
            "exit_code": 124,
            "sandboxed": True,
            "profile": str(profile),
            "error": "timeout",
        }

    return {
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "exit_code": int(proc.returncode),
        "sandboxed": True,
        "profile": str(profile),
        "argv0": argv[0],
    }
