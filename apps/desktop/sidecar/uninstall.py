"""Uninstall inventory + cleanup (M7).

Deletes managed Application Support data and crypto keys (crypto-shred).
Does **not** delete user-chosen evidence paths outside data_root — lists them.
TCC Full Disk Access cannot be revoked programmatically — returns manual steps.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.uninstall")


def _evidence_external_paths() -> List[str]:
    """Paths registered in evidence index that live outside data_root."""
    out: List[str] = []
    try:
        from apps.desktop.sidecar.evidence import get_evidence_store

        root = data_root().resolve()
        for row in get_evidence_store().list(limit=10_000):
            p = Path(str(row.get("path") or ""))
            try:
                resolved = p.expanduser().resolve()
                resolved.relative_to(root)
            except Exception:  # noqa: BLE001
                if str(p):
                    out.append(str(p))
    except Exception:  # noqa: BLE001
        pass
    return out


def inventory() -> Dict[str, Any]:
    """What uninstall will remove vs leave (read-only planning)."""
    root = data_root()
    children = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            try:
                size = (
                    sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                    if child.is_dir()
                    else child.stat().st_size
                )
            except OSError:
                size = -1
            children.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "approx_bytes": size,
                }
            )

    external = _evidence_external_paths()
    return {
        "data_root": str(root),
        "will_delete": children,
        "will_delete_secrets": True,
        "will_not_delete": {
            "evidence_outside_data_root": external,
            "note": "User-chosen artifacts are listed only; not auto-deleted (compliance).",
        },
        "manual_steps": [
            {
                "item": "TCC Full Disk Access",
                "action": (
                    "System Settings → Privacy & Security → Full Disk Access → "
                    "remove CyberGuard / Electron if listed. Cannot be revoked by the app."
                ),
            },
            {
                "item": "Application bundle",
                "action": "Move CyberGuard.app to Trash if installed under /Applications.",
            },
            {
                "item": "External evidence files",
                "action": "Delete listed paths manually if no longer needed.",
                "paths": external,
            },
        ],
        "crypto_shred": (
            "Deleting session/index keys makes encrypted session bodies unrecoverable "
            "even if residual ciphertext remains on SSD."
        ),
    }


def _purge_secrets() -> Dict[str, Any]:
    """Best-effort: wipe file backend + known keychain service prefixes."""
    from apps.desktop.sidecar import secrets_store as ss
    from apps.desktop.sidecar.data_crypto import SERVICE_INDEX, SERVICE_SESSION

    report: Dict[str, Any] = {"file_backend_cleared": False, "keychain_attempts": []}

    # File backend
    try:
        path = ss._file_path()  # noqa: SLF001 — intentional cleanup
        if path.is_file():
            path.unlink()
            report["file_backend_cleared"] = True
    except Exception as exc:  # noqa: BLE001
        report["file_error"] = type(exc).__name__

    # Index key
    try:
        ss.delete_secret(SERVICE_INDEX, "default")
        report["keychain_attempts"].append({"service": SERVICE_INDEX, "ok": True})
    except Exception:  # noqa: BLE001
        report["keychain_attempts"].append({"service": SERVICE_INDEX, "ok": False})

    # Provider
    try:
        ss.delete_secret(ss.SERVICE_PROVIDER, "default")
        report["keychain_attempts"].append({"service": ss.SERVICE_PROVIDER, "ok": True})
    except Exception:  # noqa: BLE001
        report["keychain_attempts"].append({"service": ss.SERVICE_PROVIDER, "ok": False})

    # Session keys: scan file backend already deleted; keychain session keys
    # cannot be enumerated easily — document residual risk
    report["session_keys_note"] = (
        f"Per-session keys under {SERVICE_SESSION}.* are crypto-shredded when "
        "each session is deleted; bulk keychain enumeration is not performed."
    )
    return report


def execute(*, confirm: bool = False, dry_run: bool = True) -> Dict[str, Any]:
    """Run uninstall cleanup. Requires confirm=True and dry_run=False to delete."""
    inv = inventory()
    if dry_run or not confirm:
        return {
            "ok": True,
            "dry_run": True,
            "executed": False,
            "inventory": inv,
            "message": "Pass confirm=true and dry_run=false to delete data_root + secrets.",
        }

    root = data_root()
    secrets_report = _purge_secrets()

    deleted: List[str] = []
    errors: List[str] = []
    if root.is_dir():
        try:
            # Safety: only delete if path looks like our app data
            name = root.name
            if name not in ("CyberGuard", ".cyberguard") and "cg" not in str(root).lower():
                # Allow CYBERGUARD_DATA_DIR overrides in tests (any path under tmp)
                if not os.environ.get("CYBERGUARD_DATA_DIR"):
                    raise RuntimeError(f"refusing to delete unexpected data_root: {root}")
            shutil.rmtree(root)
            deleted.append(str(root))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    try:
        from apps.desktop.sidecar.audit_chain import append_event

        # data_root may be gone — best effort if audit still writable
        append_event(
            "uninstall_executed",
            {"deleted": deleted, "errors": errors},
            approval_type="self",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": len(errors) == 0,
        "dry_run": False,
        "executed": True,
        "deleted": deleted,
        "secrets": secrets_report,
        "errors": errors,
        "manual_steps": inv["manual_steps"],
        "will_not_delete": inv["will_not_delete"],
    }
