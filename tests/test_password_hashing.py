"""Password hashing: one implementation, and it survives bcrypt >= 5.

Two defects motivated this. app/core/auth.py hashed via passlib's CryptContext,
whose bcrypt backend probes the driver with an over-length password at init —
bcrypt 5 raises there instead of truncating, so every call raised ValueError.
It went unnoticed only because the routers had each grown their own bcrypt
helper and nothing called the passlib one. Meanwhile those helpers passed the
raw password straight to bcrypt.hashpw, so any passphrase over 72 bytes was a
500 rather than a 400.
"""
from __future__ import annotations

import pytest

from app.core.auth import (
    BCRYPT_MAX_BYTES,
    PasswordTooLongError,
    get_password_hash,
    verify_password,
)


def test_hash_and_verify_round_trip():
    hashed = get_password_hash("correct horse battery staple")
    assert hashed.startswith("$2")
    assert verify_password("correct horse battery staple", hashed)


def test_a_wrong_password_does_not_verify():
    hashed = get_password_hash("s3cret-passphrase")
    assert not verify_password("s3cret-passphras", hashed)


def test_the_same_password_hashes_differently_each_time():
    """Salt must be per-hash, not global."""
    assert get_password_hash("same-input") != get_password_hash("same-input")


def test_a_password_at_the_bcrypt_limit_still_works():
    at_limit = "a" * BCRYPT_MAX_BYTES
    assert verify_password(at_limit, get_password_hash(at_limit))


def test_an_over_length_password_is_rejected_not_crashed():
    """bcrypt >= 5 raises ValueError; callers need a 400, not a 500."""
    with pytest.raises(PasswordTooLongError) as ei:
        get_password_hash("a" * (BCRYPT_MAX_BYTES + 1))
    assert str(BCRYPT_MAX_BYTES) in str(ei.value)


def test_verify_never_raises_on_hostile_input():
    hashed = get_password_hash("normal")
    assert verify_password("a" * 500, hashed) is False
    assert verify_password("normal", "not-a-bcrypt-hash") is False
    assert verify_password("", hashed) is False


def test_multibyte_passwords_are_measured_in_bytes_not_characters():
    """A 30-character CJK passphrase is 90 UTF-8 bytes — over the limit."""
    cjk = "密" * 30
    assert len(cjk) < BCRYPT_MAX_BYTES < len(cjk.encode("utf-8"))
    with pytest.raises(PasswordTooLongError):
        get_password_hash(cjk)


def test_the_routers_share_one_implementation():
    """Duplicated helpers were how the two bcrypt policies drifted apart."""
    from app.routers import auth as auth_router
    from app.routers import users as users_router

    assert auth_router.hash_password is get_password_hash
    assert users_router.hash_password is get_password_hash
    assert auth_router.verify_password is verify_password


def test_passlib_is_no_longer_a_dependency():
    """It is unmaintained and its bcrypt backend is broken against bcrypt >= 5."""
    from pathlib import Path

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith('"passlib'), f"passlib is back: {line}"
