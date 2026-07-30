"""OS sandbox facade (M2).

macOS: Seatbelt via hard-coded ``/usr/bin/sandbox-exec``.
Other platforms: report ``sandbox_impl: none`` (readonly tier only for real tools).
"""
from __future__ import annotations

from apps.desktop.sidecar.sandbox.detect import detect_sandbox_impl, sandbox_public_status
from apps.desktop.sidecar.sandbox.seatbelt import (
    SeatbeltError,
    build_profile,
    run_sandboxed,
    write_profile,
)

__all__ = [
    "SeatbeltError",
    "build_profile",
    "detect_sandbox_impl",
    "run_sandboxed",
    "sandbox_public_status",
    "write_profile",
]
