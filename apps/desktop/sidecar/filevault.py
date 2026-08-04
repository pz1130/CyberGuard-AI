"""FileVault status probe (macOS). Honest signal per INV-38 / local-data design.

We never claim app-layer encryption substitutes for FileVault.
"""
from __future__ import annotations

import platform
import subprocess
from typing import Any, Dict


def filevault_status() -> Dict[str, Any]:
    """Return FileVault status without raising.

    Fields:
      supported: bool — platform is macOS
      enabled: bool | None — True/False when known, None if unknown/non-mac
      raw: short status string
      warning: human message when not enabled (for UI banner)
    """
    if platform.system() != "Darwin":
        return {
            "supported": False,
            "enabled": None,
            "raw": "not_macos",
            "warning": None,
        }

    try:
        proc = subprocess.run(
            ["/usr/bin/fdesetup", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        raw = (proc.stdout or proc.stderr or "").strip()
        lower = raw.lower()
        if "filevault is on" in lower:
            enabled = True
        elif "filevault is off" in lower:
            enabled = False
        else:
            enabled = None
    except Exception as exc:  # noqa: BLE001
        return {
            "supported": True,
            "enabled": None,
            "raw": f"error:{type(exc).__name__}",
            "warning": (
                "Could not determine FileVault status. "
                "If full-disk encryption is off, local data may be readable if the device is lost."
            ),
        }

    warning = None
    if enabled is False:
        warning = (
            "FileVault is OFF. Full-disk encryption is not enabled on this Mac. "
            "If the device is lost or stolen, local CyberGuard data may be readable. "
            "Enable FileVault in System Settings → Privacy & Security. "
            "App-layer features do not replace full-disk encryption."
        )
    elif enabled is None:
        warning = (
            "FileVault status unknown. Verify full-disk encryption is enabled "
            "before storing sensitive investigation data."
        )

    return {
        "supported": True,
        "enabled": enabled,
        "raw": raw[:200],
        "warning": warning,
    }
