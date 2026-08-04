"""Outbound egress allowlist (defense-in-depth over SSRF block-list).

SSRF floor (private/metadata block) is ALWAYS enforced. When
EGRESS_ALLOWLIST_ENABLED, additionally require the host to match the configured
allowlist (global + optional per-call extra). Opt-in: disabled => SSRF-only.
"""
from __future__ import annotations
from urllib.parse import urlparse
from app.core.ssrf import validate_outbound_url, SSRFError  # noqa: F401


class EgressBlocked(ValueError):
    """Raised when a URL's host is not on the egress allowlist."""


def _allowlist() -> list[str]:
    from app.config import settings
    return [h.strip().lower() for h in (settings.EGRESS_ALLOWLIST or "").split(",") if h.strip()]


def _host_allowed(host: str, allow: list[str]) -> bool:
    host = (host or "").lower()
    for entry in allow:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def enforce_egress(url: str, *, extra_allow: list[str] | None = None) -> str:
    """Validate an outbound URL. Always applies the SSRF floor; applies the
    allowlist when enabled. Returns the URL on success; raises SSRFError /
    EgressBlocked otherwise."""
    validate_outbound_url(url)
    from app.config import settings
    if not settings.EGRESS_ALLOWLIST_ENABLED:
        return url
    allow = _allowlist() + [a.strip().lower() for a in (extra_allow or [])]
    host = urlparse(url).hostname or ""
    if not _host_allowed(host, allow):
        raise EgressBlocked(f"egress to {host!r} blocked — not on allowlist")
    return url
