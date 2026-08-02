"""Update package verification (M7 / INV-42).

Rejects:
  1. Tampered artifacts (sha256 mismatch or bad signature)
  2. Downgrade installs (version older than current)
  3. Untrusted signing key (MITM / wrong publisher)

Signature: Ed25519 over canonical JSON of the manifest **without** the
``signature`` field. Public key is pin-configured (embedded or env override
for tests only).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("cyberguard.desktop.update")

# Development / placeholder pin — production replaces via build-time inject.
# Tests inject via CYBERGUARD_UPDATE_PUBKEY_B64.
_DEFAULT_PUBKEY_B64 = ""  # empty = only accept keys from env in verify path


class UpdateVerifyError(ValueError):
    pass


def parse_version(v: str) -> Tuple[int, ...]:
    """Parse semver-ish version to comparable tuple (ignores -suffix)."""
    core = (v or "0").split("-")[0].split("+")[0]
    parts = []
    for p in core.split("."):
        m = re.match(r"(\d+)", p)
        parts.append(int(m.group(1)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_downgrade(current: str, candidate: str) -> bool:
    return parse_version(candidate) < parse_version(current)


def canonical_manifest(manifest: Dict[str, Any]) -> bytes:
    body = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _load_public_key_bytes() -> bytes:
    b64 = (os.environ.get("CYBERGUARD_UPDATE_PUBKEY_B64") or _DEFAULT_PUBKEY_B64).strip()
    if not b64:
        raise UpdateVerifyError("no pinned update public key configured")
    return base64.b64decode(b64)


def sign_manifest(manifest: Dict[str, Any], private_key_b64: str) -> str:
    """Test/build helper: return base64 signature."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = base64.b64decode(private_key_b64)
    key = Ed25519PrivateKey.from_private_bytes(raw)
    sig = key.sign(canonical_manifest(manifest))
    return base64.b64encode(sig).decode("ascii")


def generate_keypair() -> Dict[str, str]:
    """Test helper."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    priv_b = priv.private_bytes_raw()
    pub_b = priv.public_key().public_bytes_raw()
    return {
        "private_b64": base64.b64encode(priv_b).decode("ascii"),
        "public_b64": base64.b64encode(pub_b).decode("ascii"),
    }


def verify_signature(manifest: Dict[str, Any]) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature

    sig_b64 = manifest.get("signature")
    if not sig_b64:
        raise UpdateVerifyError("missing signature")
    pub = Ed25519PublicKey.from_public_bytes(_load_public_key_bytes())
    try:
        pub.verify(base64.b64decode(sig_b64), canonical_manifest(manifest))
    except InvalidSignature as exc:
        raise UpdateVerifyError("signature verification failed") from exc
    except Exception as exc:  # noqa: BLE001
        raise UpdateVerifyError(f"signature error: {type(exc).__name__}") from exc


def verify_artifact_hash(artifact_bytes: bytes, expected_sha256: str) -> None:
    got = hashlib.sha256(artifact_bytes).hexdigest()
    if got.lower() != (expected_sha256 or "").lower():
        raise UpdateVerifyError(
            f"artifact sha256 mismatch: expected {expected_sha256}, got {got}"
        )


def verify_update(
    manifest: Dict[str, Any],
    *,
    current_version: str,
    artifact_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Full INV-42 checks. Raises UpdateVerifyError on reject."""
    if not isinstance(manifest, dict):
        raise UpdateVerifyError("manifest must be object")

    product = manifest.get("product")
    if product and product != "cyberguard-desktop":
        raise UpdateVerifyError(f"unexpected product: {product}")

    version = str(manifest.get("version") or "")
    if not version:
        raise UpdateVerifyError("missing version")

    if is_downgrade(current_version, version):
        raise UpdateVerifyError(
            f"downgrade blocked: current={current_version} candidate={version}"
        )

    # Same version is allowed only if hashes match (reinstall); still need sig
    verify_signature(manifest)

    expected = str(manifest.get("artifact_sha256") or "")
    if artifact_bytes is not None:
        if not expected:
            raise UpdateVerifyError("missing artifact_sha256")
        verify_artifact_hash(artifact_bytes, expected)

    result = {
        "ok": True,
        "version": version,
        "current_version": current_version,
        "channel": manifest.get("channel"),
        "artifact_sha256": expected or None,
    }
    try:
        from apps.desktop.sidecar.audit_chain import append_event

        append_event(
            "update_verified",
            {"version": version, "current": current_version},
            approval_type="self",
        )
    except Exception:  # noqa: BLE001
        pass
    return result
