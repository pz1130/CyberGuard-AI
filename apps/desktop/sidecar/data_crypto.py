"""M3 local data crypto: two-tier keys + Fernet (cryptography).

Threat model (INV-38 / local-data-protection design):
  App-layer encryption supplements FileVault for **backup leakage and residual
  cleanup**. It does **not** claim protection against root or unlocked-device
  attackers. Keys live in the secrets store (Keychain or file backend).

Tiers:
  - Index key  (service=cyberguard.data.index)  — encrypts session titles / meta
  - Session key (service=cyberguard.data.session, account=<session_id>)
      — encrypts that session's JSONL body; **delete key = crypto-shred**

Uses ``cryptography.fernet`` (AES-CBC + HMAC) — not a custom cipher.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from apps.desktop.sidecar.secrets_store import (
    delete_secret,
    get_secret,
    has_secret,
    set_secret,
)

logger = logging.getLogger("cyberguard.desktop.data_crypto")

SERVICE_INDEX = "cyberguard.data.index"
SERVICE_SESSION = "cyberguard.data.session"
ACCOUNT_DEFAULT = "default"

# Magic prefix for encrypted session JSONL files
SESSION_FILE_MAGIC = "#CGSESS v1 fernet\n"


class DataCryptoError(RuntimeError):
    pass


def encryption_enabled() -> bool:
    """Allow opt-out for special drills; default ON for M3."""
    v = (os.environ.get("CYBERGUARD_SESSION_ENCRYPTION") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _fernet_from_key_b64(key_b64: str):
    from cryptography.fernet import Fernet

    return Fernet(key_b64.encode("ascii") if isinstance(key_b64, str) else key_b64)


def _generate_key_b64() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")


def ensure_index_key() -> str:
    """Return index key material (create if missing)."""
    existing = get_secret(SERVICE_INDEX, ACCOUNT_DEFAULT)
    if existing:
        return existing
    key = _generate_key_b64()
    set_secret(SERVICE_INDEX, ACCOUNT_DEFAULT, key)
    return key


def create_session_key(session_id: str) -> str:
    """Mint a fresh per-session data key. Overwrites any existing slot."""
    if not session_id:
        raise DataCryptoError("session_id required")
    key = _generate_key_b64()
    set_secret(SERVICE_SESSION, session_id, key)
    return key


def get_session_key(session_id: str) -> Optional[str]:
    if not session_id:
        return None
    return get_secret(SERVICE_SESSION, session_id)


def delete_session_key(session_id: str) -> bool:
    """Crypto-shred step: drop the only key that can decrypt the body."""
    if not session_id:
        return False
    return delete_secret(SERVICE_SESSION, session_id)


def has_session_key(session_id: str) -> bool:
    return has_secret(SERVICE_SESSION, session_id)


def encrypt_bytes(key_b64: str, plaintext: bytes) -> bytes:
    f = _fernet_from_key_b64(key_b64)
    return f.encrypt(plaintext)


def decrypt_bytes(key_b64: str, token: bytes) -> bytes:
    from cryptography.fernet import InvalidToken

    f = _fernet_from_key_b64(key_b64)
    try:
        return f.decrypt(token)
    except InvalidToken as exc:
        raise DataCryptoError("decrypt failed: invalid token or wrong key") from exc


def encrypt_text(key_b64: str, text: str) -> str:
    token = encrypt_bytes(key_b64, (text or "").encode("utf-8"))
    return token.decode("ascii")


def decrypt_text(key_b64: str, token: str) -> str:
    raw = decrypt_bytes(key_b64, token.encode("ascii"))
    return raw.decode("utf-8")


def encrypt_title(title: str) -> str:
    """Encrypt session title for index row. Returns ``enc1:<token>``."""
    if not encryption_enabled():
        return title
    key = ensure_index_key()
    return "enc1:" + encrypt_text(key, title)


def decrypt_title(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("enc1:"):
        return stored  # legacy plaintext
    if not encryption_enabled():
        return stored  # cannot decrypt if disabled mid-flight — return opaque
    key = ensure_index_key()
    try:
        return decrypt_text(key, stored[5:])
    except Exception:  # noqa: BLE001
        # Expected for legacy titles after key backend migration; SessionStore
        # recovers from first user_task. Avoid spamming WARNING logs.
        logger.debug("title decrypt failed (will try session recovery)")
        return "[encrypted title]"


def public_status() -> dict:
    return {
        "session_encryption": encryption_enabled(),
        "index_key_present": has_secret(SERVICE_INDEX, ACCOUNT_DEFAULT),
        "algorithm": "fernet",  # AES-128-CBC + HMAC via cryptography
        "claims": (
            "App-layer encryption protects against backup leakage and enables "
            "crypto-shredding. It does not replace FileVault or stop a local root."
        ),
    }
