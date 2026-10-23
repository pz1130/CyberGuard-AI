"""An email type that accepts the addresses an on-prem deployment actually uses.

Pydantic's ``EmailStr`` asks ``email-validator`` whether a domain is globally
deliverable, which rejects the special-use and reserved names — ``.local``,
``.internal``, ``.test``, ``.example`` — and bare hostnames like
``root@localhost``. For a public signup form that is the right default. This is
an admin-only user form in a product that gets installed on internal networks,
where ``ops@company.local`` is the normal thing to type, so the same default
simply made it impossible to add a user.

Syntax is still checked and the address is still normalised. What is dropped is
the opinion about whether the domain is reachable from the public internet,
which is not this product's to have.
"""
from __future__ import annotations

from typing import Annotated, Any

import email_validator
from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

# Names an on-prem deployment genuinely uses for internal mail.
_ALLOWED_SPECIAL_USE = frozenset({"local", "localhost", "test"})

# email-validator consults this module-level list and offers no per-call
# override, so the narrowing happens once, here, at import. It is deliberately
# process-wide: user creation, registration and password reset must agree about
# what an address is, or an account could be created that can never reset its
# password. "invalid" and "onion" stay rejected — those are reserved precisely
# so that they never receive mail. Re-running this is a no-op.
email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES
    if name not in _ALLOWED_SPECIAL_USE
]


def _validate(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("email must be a string")
    try:
        result = validate_email(
            value,
            # No DNS lookups: the API container must not need working
            # resolution to create a user, and a reachability check is not a
            # syntax check.
            check_deliverability=False,
            # The point of this module — allow .local, .internal, bare hosts.
            globally_deliverable=False,
        )
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized


InternalEmailStr = Annotated[str, AfterValidator(_validate)]
