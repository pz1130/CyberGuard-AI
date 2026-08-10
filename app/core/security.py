"""AES-256 encryption utilities for sensitive data."""
import base64
import hashlib
import logging
import os
from enum import Enum
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

logger = logging.getLogger(__name__)


class AESCipher:
    """AES-256 encryption/decryption utility."""

    def __init__(self, key: str):
        """Initialize with a 32-byte key."""
        if len(key) != 32:
            # Derive 32 bytes from key using SHA256
            import hashlib
            key = hashlib.sha256(key.encode()).digest()
        self.key = key.encode() if isinstance(key, str) else key

    def _pad(self, data: bytes) -> bytes:
        """Pad data to 16-byte block size."""
        padder = padding.PKCS7(128).padder()
        return padder.update(data) + padder.finalize()

    def _unpad(self, data: bytes) -> bytes:
        """Remove padding."""
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(data) + unpadder.finalize()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext and return base64-encoded ciphertext."""
        iv = os.urandom(16)
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        padded = self._pad(plaintext.encode('utf-8'))
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        # Prepend IV to ciphertext
        combined = iv + ciphertext
        return base64.b64encode(combined).decode('utf-8')

    def decrypt(self, encrypted: str) -> str:
        """Decrypt base64-encoded ciphertext and return plaintext."""
        try:
            combined = base64.b64decode(encrypted.encode('utf-8'))
            iv = combined[:16]
            ciphertext = combined[16:]
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            padded = decryptor.update(ciphertext) + decryptor.finalize()
            return self._unpad(padded).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    @staticmethod
    def generate_key() -> str:
        """Generate a random 32-byte key."""
        return base64.b64encode(os.urandom(32)).decode('utf-8')


def get_cipher():
    """Get AESCipher instance using ENCRYPTION_KEY from settings.

    Legacy read path only — see ``_decrypt_legacy_cbc``. New ciphertext is
    written by the AEAD path below.
    """
    from app.config import settings
    return AESCipher(settings.ENCRYPTION_KEY)


# ---------------------------------------------------------------------------
# AEAD (AES-256-GCM) — see docs/superpowers/specs/2026-08-10-server-credential-aead-design.md
# ---------------------------------------------------------------------------
#
# The previous scheme was unauthenticated AES-CBC. Because CBC computes
# plaintext[0] = D(ct[0]) XOR IV and the IV is stored in the clear at the head
# of the blob, anyone with database write access could rewrite the first 16
# bytes of any credential to a value of their choosing — and decryption raised
# nothing, because PKCS7 padding lives in the *last* block:
#
#     sk-live-PRODUCTION-key  ->  sk-live-ATTACKERON-key      (silently)
#
# GCM makes that a decryption failure. What this does NOT buy: anyone holding
# ENCRYPTION_KEY, process memory, or a shell on the app server is unaffected.
# The gain is precisely "database write access is no longer credential
# replacement access". Product copy must not claim more (INV-38).

_FORMAT_PREFIX = "CG2."
_ACTIVE_KEY_ID = "k1"
_NONCE_BYTES = 12


class DecryptionError(ValueError):
    """Raised for every decryption failure, with a uniform message.

    Deliberately does not distinguish padding failure from authentication
    failure from malformed input: the old code raised
    ``Decryption failed: Invalid padding bytes`` and that difference is a
    padding oracle the moment any route surfaces it. Detail goes to the log,
    never to the caller.
    """

    def __init__(self, message: str = "decryption failed"):
        super().__init__(message)


class CredentialField(str, Enum):
    """AAD values — bind a ciphertext to the field it belongs to (INV-38 §5 B).

    Stops a ciphertext being moved between columns: a webhook signing secret
    pasted into providers.api_key_encrypted no longer decrypts. It does *not*
    stop movement between rows of the same column; that was a deliberate call
    (an attacker who can do that can also repoint provider.base_url, which no
    encryption prevents).

    These strings are baked into stored ciphertext and therefore cannot change.
    If a column is ever renamed, the AAD keeps the old value.
    """

    PROVIDER_API_KEY = "providers.api_key_encrypted"
    MCP_ENV_VARS = "mcp_servers.env_vars_encrypted"
    MCP_AUTH_TOKEN = "mcp_servers.auth_token_encrypted"
    AGENT_ENV_VARS = "agent_configs.env_vars_encrypted"
    ENV_VAR_VALUE = "env_vars.value_encrypted"
    N8N_API_KEY = "n8n_connections.api_key_encrypted"
    WEBHOOK_OUTGOING_SECRET = "webhooks.outgoing_secret_encrypted"
    # Not a column: an agent's API key lives inside agent_configs.metadata_json.
    AGENT_META_API_KEY = "agent_configs.metadata_json.api_key_encrypted"
    # Declared by the model but never written or read by any call site. Kept so
    # the value is reserved if that column is ever wired up.
    KNOWLEDGE_METADATA = "knowledge_bases.metadata_encrypted"
    # Not a column either: backup dumps on disk (routers/backup.py).
    BACKUP_DUMP = "backup.dump"


def _aead_key() -> bytes:
    """Derive the k1 key.

    Identical to the legacy derivation on purpose, so the rewrite script needs
    only one key and a rollback can read either format. Note the quirk it
    preserves: ENCRYPTION_KEY is 64 hex characters, so len() != 32 and the
    *ASCII* string is hashed rather than the 32 bytes it encodes.
    """
    from app.config import settings

    key = settings.ENCRYPTION_KEY
    if len(key) == 32:
        return key.encode() if isinstance(key, str) else key
    return hashlib.sha256(key.encode()).digest()


def is_legacy_ciphertext(blob: Optional[str]) -> bool:
    """True for unauthenticated CBC ciphertext that has not been rewritten.

    Base64's alphabet contains no '.', so the prefix is unambiguous and this
    needs no trial decryption.
    """
    return bool(blob) and not str(blob).startswith(_FORMAT_PREFIX)


def encrypt_data(data: str, field: Optional[CredentialField] = None) -> str:
    """Encrypt with AES-256-GCM, binding the ciphertext to *field*."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_BYTES)
    aad = (field.value if field else "").encode("utf-8")
    sealed = AESGCM(_aead_key()).encrypt(nonce, data.encode("utf-8"), aad)
    body = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
    return f"{_FORMAT_PREFIX}{_ACTIVE_KEY_ID}.{body}"


def _decrypt_legacy_cbc(encrypted: str) -> str:
    """Read pre-AEAD ciphertext.

    NOT dead code and NOT on a deprecation clock. Backup dumps
    (routers/backup.py::_encrypt_dump) are written with this scheme to files
    that live outside the database, where no migration can reach them, and the
    entire point of a backup is that it still restores years later. This path
    is a permanent contract.
    """
    return get_cipher().decrypt(encrypted)


def decrypt_data(encrypted: str, field: Optional[CredentialField] = None) -> str:
    """Decrypt either format. Raises DecryptionError on any failure."""
    if encrypted is None:
        raise DecryptionError()

    if is_legacy_ciphertext(encrypted):
        try:
            return _decrypt_legacy_cbc(encrypted)
        except Exception as exc:  # noqa: BLE001 — uniform failure to the caller
            logger.error(
                "legacy credential decrypt failed (field=%s): %s",
                field.value if field else "unknown",
                type(exc).__name__,
            )
            raise DecryptionError() from exc

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        _, _key_id, body = encrypted.split(".", 2)
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        nonce, sealed = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        aad = (field.value if field else "").encode("utf-8")
        return AESGCM(_aead_key()).decrypt(nonce, sealed, aad).decode("utf-8")
    except InvalidTag as exc:
        # INV-25: an authentication failure is a tampering signal, not routine.
        # Loud, with the field, and without the ciphertext or the plaintext.
        logger.error(
            "CREDENTIAL TAMPERING SUSPECTED: authentication tag mismatch "
            "(field=%s). The stored value was modified, or a ciphertext from "
            "another field was moved here.",
            field.value if field else "unknown",
        )
        raise DecryptionError() from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "credential decrypt failed (field=%s): %s",
            field.value if field else "unknown",
            type(exc).__name__,
        )
        raise DecryptionError() from exc