"""Encrypted export of local CyberGuard data (M7).

Prefer ``age`` CLI when available (standard format, client-decryptable without
our app). Fallback: passphrase-protected archive using PBKDF2-HMAC-SHA256 +
Fernet (cryptography), documented header so tools can be written independently.

Never includes raw Keychain secrets or provider API keys in the clear.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.export")

# Format magic for fallback envelope
CGX_MAGIC = b"CGX1"
DEFAULT_INCLUDE = (
    "sessions",
    "audit",
    "evidence",
    "episodic",
    "trust.json",
)


def _age_available() -> bool:
    return shutil.which("age") is not None


def _collect_paths(include: Sequence[str]) -> List[Path]:
    root = data_root()
    out: List[Path] = []
    for name in include:
        p = root / name if not name.startswith("/") else Path(name)
        if not p.is_absolute():
            p = root / name
        if p.exists():
            out.append(p)
    return out


def _tar_bytes(paths: Sequence[Path], *, root: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in paths:
            arcname = p.relative_to(root) if str(p).startswith(str(root)) else p.name
            tar.add(str(p), arcname=str(arcname), recursive=True)
        # Manifest inside archive
        meta = {
            "exported_at": time.time(),
            "app": "cyberguard-desktop",
            "paths": [str(p) for p in paths],
            "note": "Encrypted export — keys not included; sessions may be ciphertext without keys.",
        }
        data = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="export_manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _encrypt_fernet_passphrase(plaintext: bytes, passphrase: str) -> bytes:
    """PBKDF2 + Fernet envelope: CGX1 | salt(16) | token."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if not passphrase:
        raise ValueError("passphrase required")
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    token = Fernet(key).encrypt(plaintext)
    return CGX_MAGIC + salt + token


def decrypt_fernet_passphrase(blob: bytes, passphrase: str) -> bytes:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if not blob.startswith(CGX_MAGIC):
        raise ValueError("not a CGX1 envelope")
    salt = blob[4:20]
    token = blob[20:]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key).decrypt(token)


def _encrypt_age_recipient(plaintext: bytes, recipient: str) -> bytes:
    """Encrypt with age -r RECIPIENT (public key)."""
    proc = subprocess.run(
        ["age", "-r", recipient, "-o", "-"],
        input=plaintext,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"age encrypt failed: {err}")
    return proc.stdout


def _encrypt_age_passphrase(plaintext: bytes, passphrase: str) -> bytes:
    """age -p (passphrase). Uses AGE_PASSPHRASE env for non-interactive."""
    env = os.environ.copy()
    env["AGE_PASSPHRASE"] = passphrase
    proc = subprocess.run(
        ["age", "-p", "-o", "-"],
        input=plaintext,
        capture_output=True,
        check=False,
        env=env,
    )
    if proc.returncode != 0:
        # Some age builds need --passphrase
        proc = subprocess.run(
            ["age", "--passphrase", "-o", "-"],
            input=plaintext,
            capture_output=True,
            check=False,
            env=env,
        )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"age passphrase encrypt failed: {err}")
    return proc.stdout


def export_encrypted(
    dest_path: str | Path,
    *,
    passphrase: Optional[str] = None,
    age_recipient: Optional[str] = None,
    include: Optional[Sequence[str]] = None,
    prefer_age: bool = True,
) -> Dict[str, Any]:
    """Write encrypted export archive to dest_path.

    Provide either ``passphrase`` or ``age_recipient`` (age public key).
    """
    dest = Path(dest_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    names = list(include) if include is not None else list(DEFAULT_INCLUDE)
    root = data_root()
    paths = _collect_paths(names)
    if not paths:
        raise FileNotFoundError("nothing to export under data root")

    raw = _tar_bytes(paths, root=root)
    digest = hashlib.sha256(raw).hexdigest()
    method = "cgx1-fernet"
    blob: bytes

    if prefer_age and _age_available() and age_recipient:
        blob = _encrypt_age_recipient(raw, age_recipient)
        method = "age-recipient"
    elif prefer_age and _age_available() and passphrase:
        try:
            blob = _encrypt_age_passphrase(raw, passphrase)
            method = "age-passphrase"
        except Exception as exc:  # noqa: BLE001
            logger.warning("age passphrase failed (%s); falling back to CGX1", type(exc).__name__)
            if not passphrase:
                raise
            blob = _encrypt_fernet_passphrase(raw, passphrase)
            method = "cgx1-fernet"
    elif passphrase:
        blob = _encrypt_fernet_passphrase(raw, passphrase)
        method = "cgx1-fernet"
    else:
        raise ValueError("passphrase or age_recipient required")

    dest.write_bytes(blob)
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass

    result = {
        "ok": True,
        "path": str(dest.resolve()),
        "method": method,
        "plaintext_sha256": digest,
        "bytes": len(blob),
        "included": [str(p) for p in paths],
        "age_available": _age_available(),
    }
    try:
        from apps.desktop.sidecar.audit_chain import append_event

        append_event(
            "export_encrypted",
            {
                "method": method,
                "bytes": len(blob),
                "plaintext_sha256": digest,
                "dest_name": dest.name,
            },
            approval_type="self",
        )
    except Exception:  # noqa: BLE001
        pass
    return result
