"""macOS TCC (Transparency, Consent, Control) probe for M2 status bar.

We do **not** claim Full Disk Access via private APIs. Instead we probe whether
common evidence locations are listable/readable — the same failure mode analysts
hit when TCC silently denies ("file not found").

Honest signals only (INV-38).
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _probe_listable(path: Path) -> Tuple[bool, Optional[str]]:
    try:
        if not path.exists():
            # Missing dir is not a TCC denial — report as skipped
            return True, "missing"
        # iterdir may raise PermissionError under TCC on some locations
        next(iter(path.iterdir()), None)
        return True, None
    except PermissionError:
        return False, "permission_denied"
    except OSError as exc:
        # Some TCC failures surface as EPERM OSError
        if getattr(exc, "errno", None) in (1, 13):  # EPERM, EACCES
            return False, f"os_error:{exc.errno}"
        return False, f"os_error:{type(exc).__name__}"


def _probe_readable_file(path: Path) -> Tuple[bool, Optional[str]]:
    try:
        if not path.exists():
            return True, "missing"
        with path.open("rb") as f:
            f.read(1)
        return True, None
    except PermissionError:
        return False, "permission_denied"
    except OSError as exc:
        if getattr(exc, "errno", None) in (1, 13):
            return False, f"os_error:{exc.errno}"
        return False, f"os_error:{type(exc).__name__}"


def tcc_status() -> Dict[str, Any]:
    """Return TCC/probe status for UI and ping.

    Fields:
      supported: macOS only
      locations: list of {id, path, ok, detail}
      sensitive_ok: bool | None — all present sensitive locations ok
      full_disk_access: bool | None — heuristic only
      warning: str | None
      guidance: str | None — how to fix in System Settings
    """
    if platform.system() != "Darwin":
        return {
            "supported": False,
            "locations": [],
            "sensitive_ok": None,
            "full_disk_access": None,
            "warning": None,
            "guidance": None,
            "summary": "not_macos",
        }

    home = Path.home()
    probes: List[Tuple[str, Path, str]] = [
        ("desktop", home / "Desktop", "list"),
        ("documents", home / "Documents", "list"),
        ("downloads", home / "Downloads", "list"),
        # FDA often required for these (may be missing — then skipped)
        ("mail_library", home / "Library" / "Mail", "list"),
        (
            "tcc_db",
            home / "Library" / "Application Support" / "com.apple.TCC" / "TCC.db",
            "file",
        ),
    ]

    locations: List[Dict[str, Any]] = []
    blocked: List[str] = []
    present_checked = 0
    present_ok = 0
    tcc_db_ok: Optional[bool] = None

    for loc_id, path, kind in probes:
        if kind == "list":
            ok, detail = _probe_listable(path)
        else:
            ok, detail = _probe_readable_file(path)

        entry = {
            "id": loc_id,
            "path": str(path),
            "ok": ok,
            "detail": detail,
        }
        locations.append(entry)

        if detail == "missing":
            continue
        present_checked += 1
        if ok:
            present_ok += 1
        else:
            blocked.append(loc_id)

        if loc_id == "tcc_db":
            tcc_db_ok = ok if detail != "missing" else None

    # Heuristic Full Disk Access:
    # - True if TCC.db readable (strong signal)
    # - False if common user folders are blocked
    # - None if ambiguous (all missing / no clear deny)
    full_disk_access: Optional[bool]
    if tcc_db_ok is True:
        full_disk_access = True
    elif any(
        loc["id"] in ("desktop", "documents", "downloads")
        and loc["ok"] is False
        and loc.get("detail") != "missing"
        for loc in locations
    ):
        full_disk_access = False
    elif tcc_db_ok is False:
        # TCC.db unreadable is common even with some folder access — not decisive alone
        full_disk_access = None
    else:
        full_disk_access = None

    sensitive_ok: Optional[bool]
    if present_checked == 0:
        sensitive_ok = None
    else:
        sensitive_ok = present_ok == present_checked

    warning = None
    guidance = None
    if blocked:
        names = ", ".join(blocked)
        warning = (
            f"TCC may block host reads for: {names}. "
            "macOS often fails silently (looks like missing files). "
            "Grant Full Disk Access to Terminal/Electron/your signed app bundle "
            "if you need Desktop/Documents/Downloads or mail evidence."
        )
        guidance = (
            "System Settings → Privacy & Security → Full Disk Access → "
            "enable this app (or the terminal that launches it). "
            "Dev builds may lose TCC after re-signing — see docs/desktop/10-DEV-SETUP.md."
        )
    elif full_disk_access is None:
        # Soft note only when we couldn't confirm FDA — not a hard warning banner
        guidance = (
            "Full Disk Access not confirmed. If host reads of Desktop/Documents fail, "
            "grant FDA in System Settings → Privacy & Security."
        )

    if full_disk_access is True:
        summary = "fda_likely"
    elif full_disk_access is False or blocked:
        summary = "restricted"
    else:
        summary = "unknown"

    return {
        "supported": True,
        "locations": locations,
        "sensitive_ok": sensitive_ok,
        "full_disk_access": full_disk_access,
        "warning": warning,
        "guidance": guidance,
        "summary": summary,
    }
