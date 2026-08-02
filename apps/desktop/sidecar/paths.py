"""Managed local paths for the desktop sidecar (M1).

Sensitive data MUST stay under the app data root — never ad-hoc /tmp.
See docs/superpowers/specs/2026-07-29-local-data-protection-design.md.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


APP_NAME = "CyberGuard"


def data_root() -> Path:
    """User-scoped application data root.

    Override with CYBERGUARD_DATA_DIR (tests / portable installs).
    Default: ~/Library/Application Support/CyberGuard on macOS,
    else ~/.cyberguard.
    """
    override = os.environ.get("CYBERGUARD_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    else:
        try:
            is_darwin = os.uname().sysname == "Darwin"
        except Exception:
            is_darwin = sys.platform == "darwin"
        if is_darwin:
            root = Path.home() / "Library" / "Application Support" / APP_NAME
        else:
            root = Path.home() / ".cyberguard"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sessions_dir() -> Path:
    p = data_root() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_root() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def tmp_dir() -> Path:
    """Managed temp — NOT system /tmp for sensitive intermediates."""
    p = data_root() / "tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def workspace_dir() -> Path:
    """Agent-writable workspace under managed data root (M2 workspace-write)."""
    p = data_root() / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def audit_dir() -> Path:
    p = data_root() / "audit"
    p.mkdir(parents=True, exist_ok=True)
    return p


def episodic_dir() -> Path:
    """Local episodic experience store (M3 VectorIndex standalone)."""
    p = data_root() / "episodic"
    p.mkdir(parents=True, exist_ok=True)
    return p


def episodic_db() -> Path:
    return episodic_dir() / "index.sqlite3"


def session_jsonl_path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return sessions_dir() / f"{safe}.jsonl"


def session_index_db() -> Path:
    return sessions_dir() / "index.sqlite3"


def managed_tempfile(suffix: str = "", prefix: str = "cg-") -> Path:
    """Create an empty temp file under managed tmp_dir (caller writes)."""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(tmp_dir()))
    os.close(fd)
    return Path(name)


def assert_under_data_root(path: Path) -> None:
    """Raise if path escapes the managed data root (INV data boundary)."""
    root = data_root().resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes data root: {resolved} not under {root}") from exc
