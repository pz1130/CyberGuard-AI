"""Detect available OS sandbox implementation."""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, Literal

SandboxImpl = Literal["seatbelt", "none"]

SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def detect_sandbox_impl() -> SandboxImpl:
    if platform.system() == "Darwin" and Path(SANDBOX_EXEC).is_file():
        return "seatbelt"
    return "none"


def sandbox_public_status() -> Dict[str, Any]:
    impl = detect_sandbox_impl()
    return {
        "sandbox_impl": impl,
        "sandbox_exec": SANDBOX_EXEC if impl == "seatbelt" else None,
        "os": platform.system(),
        "arch": platform.machine(),
        "pid": os.getpid(),
        "warning": (
            None
            if impl != "none"
            else "No OS sandbox available — real host tools must stay disabled (INV-16)."
        ),
    }
