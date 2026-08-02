"""Mark sensitive data directories as excluded from system backups (M3).

Targets Time Machine / iCloud-style backup of:
  sessions/, episodic/, tmp/, workspace/, audit/

Does **not** exclude skills/ or ordinary config (design §6).

macOS: xattr ``com.apple.metadata:com_apple_backup_excludeItem``
All platforms: write a ``.cg-nobackup`` marker file inside each dir.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from apps.desktop.sidecar.paths import (
    audit_dir,
    data_root,
    episodic_dir,
    sessions_dir,
    tmp_dir,
    workspace_dir,
)

logger = logging.getLogger("cyberguard.desktop.backup_exclude")

MARKER_NAME = ".cg-nobackup"
# Apple Time Machine exclusion xattr (boolean plist true as single byte is common;
# we use the documented attribute name with empty-or-true value).
XATTR_NAME = "com.apple.metadata:com_apple_backup_excludeItem"


def sensitive_dirs() -> List[Path]:
    return [
        sessions_dir(),
        episodic_dir(),
        tmp_dir(),
        workspace_dir(),
        audit_dir(),
    ]


def _write_marker(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER_NAME
    if not marker.is_file():
        marker.write_text(
            "CyberGuard: exclude this directory from backups.\n"
            "See docs/superpowers/specs/2026-07-29-local-data-protection-design.md\n",
            encoding="utf-8",
        )


def _xattr_exclude(path: Path) -> bool:
    """Best-effort Time Machine exclusion. Returns True if applied."""
    if platform.system() != "Darwin":
        return False
    try:
        # xattr -w name value path
        # Value "1" is accepted by many tooling; empty also works on some systems.
        proc = subprocess.run(
            ["/usr/bin/xattr", "-w", XATTR_NAME, "1", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("xattr exclude failed for %s: %s", path, type(exc).__name__)
        return False


def _has_xattr(path: Path) -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        proc = subprocess.run(
            ["/usr/bin/xattr", "-p", XATTR_NAME, str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def apply_exclusions() -> Dict[str, Any]:
    """Ensure sensitive dirs exist and are marked. Idempotent."""
    results = []
    for d in sensitive_dirs():
        try:
            _write_marker(d)
            xattr_ok = _xattr_exclude(d)
            results.append(
                {
                    "path": str(d),
                    "marker": (d / MARKER_NAME).is_file(),
                    "xattr": xattr_ok or _has_xattr(d),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "path": str(d),
                    "marker": False,
                    "xattr": False,
                    "error": type(exc).__name__,
                }
            )
    # Also mark data_root itself for secrets.json etc. when present under root
    try:
        root = data_root()
        _write_marker(root)
        _xattr_exclude(root)
    except Exception:  # noqa: BLE001
        pass
    return {
        "dirs": results,
        "platform": platform.system(),
        "xattr_name": XATTR_NAME if platform.system() == "Darwin" else None,
    }


def public_status() -> Dict[str, Any]:
    dirs = []
    for d in sensitive_dirs():
        marker = d / MARKER_NAME
        dirs.append(
            {
                "path": str(d),
                "marker": marker.is_file(),
                "xattr": _has_xattr(d),
            }
        )
    return {"excluded_dirs": dirs, "platform": platform.system()}
