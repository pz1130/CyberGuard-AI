"""An on-prem deployment must be able to create users with internal emails.

`EmailStr` rejects special-use and reserved domains — `.local`, `.test`,
`.example` — and bare hostnames. That is the right default for a public signup
form and the wrong one here: this is an admin-only form in a security product
that gets installed on internal networks, where `ops@company.local` is the
normal thing to type. The result was that adding a local user simply failed.

Syntax is still validated. What is dropped is the judgement about whether the
domain is reachable from the public internet, which is not this product's
business to have an opinion about.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


def _make(email: str) -> UserCreate:
    return UserCreate(username="someone", email=email, password="Str0ng-Pass-123")


@pytest.mark.parametrize("email", [
    "ops@acme-corp.com",
    "ops@example.com",
    "first.last+tag@acme-corp.co.uk",
])
def test_ordinary_public_addresses_still_work(email):
    assert _make(email).email == email


@pytest.mark.parametrize("email", [
    "ops@company.local",       # the most common on-prem convention
    "ops@corp.test",
    "ops@cyberguard.internal",
    "ops@site.example",
    "root@localhost",          # bare hostname; legal, and real on a host
    "ops@intranet",
])
def test_internal_addresses_are_accepted(email):
    """Each of these was a 422 before, which is what blocked local users."""
    assert _make(email).email == email


@pytest.mark.parametrize("email", [
    "not-an-email",            # no @
    "@no-local-part.com",
    "two@@ats.com",
    "trailing-dot@domain.",
    "",
    "spaces in@domain.com",
])
def test_genuinely_malformed_addresses_are_still_rejected(email):
    """Loosening the domain rule must not turn the field into a free-text box."""
    with pytest.raises(ValidationError):
        _make(email)


def test_the_address_is_normalised_not_merely_accepted():
    """email-validator lowercases the domain; storing both cases would let two
    rows differ only by case and defeat the uniqueness check in create_user."""
    assert _make("Ops@ACME-Corp.COM").email == "Ops@acme-corp.com"


def test_the_update_schema_accepts_the_same_addresses():
    """A user creatable with an internal address must also be editable."""
    from app.schemas.user import UserUpdate

    assert UserUpdate(email="ops@company.local").email == "ops@company.local"
    assert UserUpdate().email is None


@pytest.mark.parametrize("email", [
    "ops@something.invalid",   # reserved so that it never resolves
    "ops@abcdef.onion",        # Tor; not a mail destination
])
def test_names_reserved_to_never_receive_mail_stay_rejected(email):
    """Loosening for .local must not loosen for names that exist to be undeliverable."""
    with pytest.raises(ValidationError):
        _make(email)


def test_registration_and_password_reset_agree_with_user_creation():
    """An account creatable with an internal address must be able to reset its
    password, or it is an account that can never be recovered."""
    from app.schemas.auth import PasswordResetRequest, RegisterRequest

    assert RegisterRequest(username="someone", email="ops@company.local",
                           password="Str0ng-Pass-123").email == "ops@company.local"
    assert PasswordResetRequest(email="ops@company.local").email == "ops@company.local"
