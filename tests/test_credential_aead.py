"""Server credential encryption — the §9 acceptance criteria.

Design: docs/superpowers/specs/2026-08-10-server-credential-aead-design.md

The scheme this replaces was unauthenticated AES-CBC. Because CBC computes
plaintext[0] = D(ct[0]) XOR IV and the IV sits in the clear at the head of the
blob — while PKCS7 padding lives in the *last* block — anyone with database
write access could rewrite the first 16 bytes of a credential to a value of
their choosing and decryption raised nothing at all.
"""
from __future__ import annotations

import base64

import pytest

from app.config import settings
from app.core.security import (
    AESCipher,
    CredentialField,
    DecryptionError,
    decrypt_data,
    encrypt_data,
    is_legacy_ciphertext,
)

FIELD = CredentialField.PROVIDER_API_KEY
SECRET = "sk-live-PRODUCTION-key"


def _legacy(plaintext: str) -> str:
    """Ciphertext exactly as the pre-AEAD code produced it."""
    return AESCipher(settings.ENCRYPTION_KEY).encrypt(plaintext)


def _corrupt(blob: str, index: int = 0) -> str:
    raw = bytearray(base64.urlsafe_b64decode(blob.split(".", 2)[2]))
    raw[index] ^= 1
    head = blob.rsplit(".", 1)[0]
    return f"{head}.{base64.urlsafe_b64encode(bytes(raw)).decode()}"


# --- the defect that motivated all of this ---------------------------------


def test_the_cbc_forgery_that_used_to_succeed_now_fails():
    """§9's core criterion. This exact manipulation was silent before.

    Reproduces the old attack in full: flip IV bits so the first plaintext
    block becomes attacker-chosen. Under CBC this yielded
    'sk-live-ATTACKERON-key' with no error raised.
    """
    legacy = _legacy(SECRET)
    raw = bytearray(base64.b64decode(legacy))
    target = b"sk-live-ATTACKER!!-key"
    for i in range(16):
        raw[i] ^= SECRET.encode()[i] ^ target[i]
    forged_legacy = base64.b64encode(bytes(raw)).decode()

    # The old scheme: forgery accepted, no error. Asserted so the regression
    # this fixes stays documented rather than becoming folklore.
    assert AESCipher(settings.ENCRYPTION_KEY).decrypt(forged_legacy) != SECRET

    # The new scheme: the same class of manipulation is rejected.
    sealed = encrypt_data(SECRET, FIELD)
    with pytest.raises(DecryptionError):
        decrypt_data(_corrupt(sealed), FIELD)


@pytest.mark.parametrize("index", [0, 5, 12, 20])
def test_flipping_any_bit_anywhere_is_detected(index):
    sealed = encrypt_data(SECRET, FIELD)
    with pytest.raises(DecryptionError):
        decrypt_data(_corrupt(sealed, index), FIELD)


# --- AAD tier B: a ciphertext is bound to its field -------------------------


def test_a_ciphertext_cannot_be_moved_to_another_field():
    """A webhook secret pasted into providers.api_key_encrypted must not read."""
    sealed = encrypt_data("whsec_abc", CredentialField.WEBHOOK_OUTGOING_SECRET)
    assert decrypt_data(sealed, CredentialField.WEBHOOK_OUTGOING_SECRET) == "whsec_abc"

    with pytest.raises(DecryptionError):
        decrypt_data(sealed, CredentialField.PROVIDER_API_KEY)


def test_every_field_has_a_distinct_aad():
    values = [f.value for f in CredentialField]
    assert len(values) == len(set(values))


def test_moving_between_rows_of_one_field_is_not_prevented():
    """Tier B, chosen deliberately — this documents the boundary, not a bug.

    Blocking it needs the row id inside the AAD, which is unavailable at INSERT
    time. It was judged not worth it: an attacker who can swap rows can also
    repoint provider.base_url, which no encryption scheme prevents. The
    security claim must not overreach (INV-38).
    """
    a = encrypt_data("key-for-provider-1", FIELD)
    assert decrypt_data(a, FIELD) == "key-for-provider-1"


# --- format ----------------------------------------------------------------


def test_new_ciphertext_is_tagged_and_versioned():
    sealed = encrypt_data(SECRET, FIELD)
    assert sealed.startswith("CG2.k1.")
    assert not is_legacy_ciphertext(sealed)


def test_legacy_ciphertext_is_recognised_without_trial_decryption():
    assert is_legacy_ciphertext(_legacy(SECRET))
    # base64's alphabet has no '.', so the prefix test cannot collide
    assert "." not in _legacy(SECRET)


def test_the_same_plaintext_encrypts_differently_each_time():
    assert encrypt_data(SECRET, FIELD) != encrypt_data(SECRET, FIELD)


def test_round_trip_survives_unicode_and_empty_values():
    for value in ["", "sk-ünïcodé-🔐", "x" * 10_000, '{"json": "payload"}']:
        assert decrypt_data(encrypt_data(value, FIELD), FIELD) == value


# --- legacy read path is a permanent contract -------------------------------


def test_legacy_ciphertext_still_decrypts():
    assert decrypt_data(_legacy("old-secret"), FIELD) == "old-secret"


def test_legacy_reads_ignore_the_aad_field():
    """Old ciphertext predates AAD; any field must still read it.

    Backup dumps live on disk outside the database, and the point of a backup
    is that it still restores years later.
    """
    legacy = _legacy("old-secret")
    for field in (FIELD, CredentialField.BACKUP_DUMP, CredentialField.ENV_VAR_VALUE):
        assert decrypt_data(legacy, field) == "old-secret"


def test_the_legacy_reader_is_marked_as_permanent():
    """Guard against a future cleanup deleting it as dead code."""
    import inspect

    from app.core.security import _decrypt_legacy_cbc

    doc = inspect.getdoc(_decrypt_legacy_cbc) or ""
    assert "NOT dead code" in doc


# --- no padding oracle ------------------------------------------------------


def test_every_failure_mode_reports_the_same_message():
    """Distinguishable failures are how a padding oracle starts.

    The old code raised 'Decryption failed: Invalid padding bytes' for one and
    something else for another.
    """
    sealed = encrypt_data(SECRET, FIELD)
    failures = [
        _corrupt(sealed),                                  # bad auth tag
        "CG2.k1.!!!not-base64!!!",                         # malformed body
        "CG2.k1.",                                         # empty body
        base64.b64encode(b"x" * 48).decode(),              # bad legacy padding
        base64.b64encode(b"y" * 32).decode(),              # bad legacy content
    ]
    messages = set()
    for blob in failures:
        with pytest.raises(DecryptionError) as ei:
            decrypt_data(blob, FIELD)
        messages.add(str(ei.value))

    assert len(messages) == 1, f"failure modes are distinguishable: {messages}"


def test_failures_never_echo_the_ciphertext_or_plaintext():
    sealed = encrypt_data(SECRET, FIELD)
    with pytest.raises(DecryptionError) as ei:
        decrypt_data(_corrupt(sealed), FIELD)
    assert SECRET not in str(ei.value)
    assert sealed not in str(ei.value)


def test_tampering_is_logged_loudly(caplog):
    """INV-25: an authentication failure is a security signal, not routine."""
    import logging

    sealed = encrypt_data(SECRET, FIELD)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(DecryptionError):
            decrypt_data(_corrupt(sealed), FIELD)

    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "TAMPERING" in logged
    assert FIELD.value in logged
    assert SECRET not in logged


# --- every call site is bound ----------------------------------------------


def test_no_call_site_encrypts_without_naming_its_field():
    """An unbound ciphertext silently opts out of the cross-field guarantee."""
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    offenders = []
    for path in (repo / "app").rglob("*.py"):
        if path.name in ("security.py", "__init__.py"):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "encrypt_data(" in line or "decrypt_data(" in line:
                if "import" in line or "def " in line:
                    continue
                # multi-line calls carry the field on the following line
                if "CredentialField" in line:
                    continue
                if line.rstrip().endswith("encrypt_data(") or line.rstrip().endswith(
                    "decrypt_data("
                ):
                    continue
                offenders.append(f"{path.relative_to(repo)}:{lineno}: {line.strip()}")

    assert offenders == [], "unbound credential crypto calls:\n" + "\n".join(offenders)
