"""Field-level before/after for privileged changes, without the secrets.

The HTTP middleware records that someone called an endpoint and how it ended,
but not the request body — logging bodies wholesale would put passwords, API
keys and uploaded files into the audit table, which is a worse problem than the
gap it closes.

For the few operations that move authority around — roles, governance settings,
credentials — the trail needs to say *what* changed. This produces that, with
credential-shaped fields reduced to "it changed" and nothing more.

Pure and DB-free, like ``app.core.pii``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional


class _Redacted:
    """A value that must not be written down. Distinct from None and from ''."""

    __slots__ = ()

    def __repr__(self) -> str:  # what lands in the audit row
        return "[REDACTED]"

    def __str__(self) -> str:
        return "[REDACTED]"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Redacted)

    def __hash__(self) -> int:
        return hash("[REDACTED]")


REDACTED = _Redacted()

# Matched against the field name with separators and case removed, so
# `api_key`, `apiKey` and `API-KEY` are all caught by one entry.
_SECRET_MARKERS = (
    "password", "apikey", "secret", "token", "credential",
    "privatekey", "envvars", "passphrase",
)

MAX_VALUE_CHARS = 500


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def is_secret_field(name: str) -> bool:
    flat = _normalize(name)
    return any(marker in flat for marker in _SECRET_MARKERS)


def _shorten(value: Any) -> Any:
    """Keep one field from flooding the trail, without hiding what changed."""
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return value[:MAX_VALUE_CHARS] + f"… (+{len(value) - MAX_VALUE_CHARS} chars)"
    return value


def field_diff(
    before: Optional[Mapping[str, Any]],
    after: Optional[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """``{field: {"from": old, "to": new}}`` for the fields *after* mentions.

    Only keys present in ``after`` are considered, so a partial update does not
    read as "every other field was cleared". A credential-shaped field records
    that it changed and never what it changed to.
    """
    before = before or {}
    after = after or {}

    changes: Dict[str, Dict[str, Any]] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value == new_value:
            continue
        if is_secret_field(key):
            changes[key] = {"from": REDACTED, "to": REDACTED}
        else:
            changes[key] = {"from": _shorten(old_value), "to": _shorten(new_value)}
    return changes
