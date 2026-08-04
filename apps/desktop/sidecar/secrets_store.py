"""Local secrets store (M3): Keychain slots + test/file fallback.

Service naming (DEC-018 style):
  - provider API key:  service=cyberguard.provider  account=default
  - MCP server secret: service=cyberguard.mcp       account=<server_id>

Never log secret values. Cross-slot reads are not provided by design —
callers must pass the exact service/account they own.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import Dict, Optional

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.secrets")

SERVICE_PROVIDER = "cyberguard.provider"
SERVICE_MCP_PREFIX = "cyberguard.mcp"  # full service = cyberguard.mcp.<id>


class SecretsError(RuntimeError):
    pass


def mcp_service(server_id: str) -> str:
    sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (server_id or ""))
    if not sid:
        raise SecretsError("mcp server_id required")
    return f"{SERVICE_MCP_PREFIX}.{sid}"


def _backend() -> str:
    # file | keychain | auto
    b = (os.environ.get("CYBERGUARD_SECRETS_BACKEND") or "auto").strip().lower()
    if b in ("file", "keychain"):
        return b
    # auto: if secrets.json already has data (e.g. headless migrate / tests),
    # keep using file so Electron does not look at empty Keychain and drop keys.
    try:
        if _file_path().is_file() and _file_load():
            return "file"
    except Exception:  # noqa: BLE001
        pass
    return "keychain" if platform.system() == "Darwin" else "file"


def _file_path() -> Path:
    return data_root() / "secrets.json"


def _file_load() -> Dict[str, Dict[str, str]]:
    path = _file_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _file_save(data: Dict[str, Dict[str, str]]) -> None:
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _keychain_get(service: str, account: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("keychain get failed: %s", type(exc).__name__)
        return None
    if proc.returncode != 0:
        return None
    # -w prints password with trailing newline
    return (proc.stdout or "").rstrip("\n")


def _keychain_set(service: str, account: str, secret: str) -> None:
    # delete existing then add (idempotent)
    subprocess.run(
        [
            "/usr/bin/security",
            "delete-generic-password",
            "-s",
            service,
            "-a",
            account,
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    proc = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            secret,
            "-U",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "keychain set failed").strip()
        raise SecretsError(f"keychain set failed: {err[:200]}")


def _keychain_delete(service: str, account: str) -> bool:
    proc = subprocess.run(
        [
            "/usr/bin/security",
            "delete-generic-password",
            "-s",
            service,
            "-a",
            account,
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    return proc.returncode == 0


def get_secret(service: str, account: str = "default") -> Optional[str]:
    if not service or not account:
        raise SecretsError("service and account required")
    backend = _backend()
    if backend == "keychain":
        val = _keychain_get(service, account)
        if val:
            return val
        # Fallback: file store may hold keys after headless migrate
        data = _file_load()
        slot = data.get(service) or {}
        fv = slot.get(account)
        return str(fv) if fv else None
    data = _file_load()
    slot = data.get(service) or {}
    val = slot.get(account)
    if val:
        return str(val)
    # Fallback: Keychain may hold older index/session keys (title decrypt recovery)
    if platform.system() == "Darwin":
        return _keychain_get(service, account)
    return None


def set_secret(service: str, account: str, secret: str) -> None:
    if not service or not account:
        raise SecretsError("service and account required")
    if secret is None or secret == "":
        raise SecretsError("secret must be non-empty")
    backend = _backend()
    if backend == "keychain":
        _keychain_set(service, account, secret)
        return
    data = _file_load()
    data.setdefault(service, {})[account] = secret
    _file_save(data)


def delete_secret(service: str, account: str = "default") -> bool:
    if not service or not account:
        raise SecretsError("service and account required")
    backend = _backend()
    if backend == "keychain":
        return _keychain_delete(service, account)
    data = _file_load()
    slot = data.get(service) or {}
    if account not in slot:
        return False
    del slot[account]
    if not slot:
        data.pop(service, None)
    else:
        data[service] = slot
    _file_save(data)
    return True


def has_secret(service: str, account: str = "default") -> bool:
    return bool(get_secret(service, account))


def public_status() -> dict:
    """Safe for ping — no secret values."""
    backend = _backend()
    return {
        "backend": backend,
        "provider_key_present": has_secret(SERVICE_PROVIDER, "default"),
        "platform": platform.system(),
    }


def get_provider_api_key() -> Optional[str]:
    return get_secret(SERVICE_PROVIDER, "default")


def set_provider_api_key(api_key: str) -> None:
    set_secret(SERVICE_PROVIDER, "default", api_key)


def get_mcp_secret(server_id: str) -> Optional[str]:
    return get_secret(mcp_service(server_id), "default")


def set_mcp_secret(server_id: str, secret: str) -> None:
    set_secret(mcp_service(server_id), "default", secret)


def delete_mcp_secret(server_id: str) -> bool:
    return delete_secret(mcp_service(server_id), "default")
