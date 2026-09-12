"""Shared SSRF protection — resolve hostname to IP and block private ranges.

All outbound URL validation (agents, providers, MCP, OpenClaw) should
use :func:`validate_outbound_url` to prevent server-side request forgery.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# RFC 1918 + link-local + cloud metadata + loopback + unspecified
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/32"),       # unspecified (binds to all local interfaces)
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),    # link-local + cloud metadata
    ipaddress.ip_network("::/128"),            # IPv6 unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6 (covers ::ffff:127.0.0.1 etc.)
]

# Hostnames that resolve to metadata endpoints (checked before DNS)
_BLOCKED_HOSTNAMES = frozenset({
    "169.254.169.254",          # AWS / Azure metadata
    "metadata.google.internal",  # GCP metadata
    "metadata.internal",
    "metadata.azure.com",
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
})


class SSRFError(ValueError):
    """Raised when a URL fails SSRF validation."""


def validate_outbound_url(url: str) -> str:
    """Validate a URL for safe outbound requests.

    Checks:
    1. Scheme is http or https
    2. Hostname is not in the blocked list
    3. Hostname resolves to a non-private IP (DNS resolution)

    Returns the original URL on success.
    Raises :class:`SSRFError` on failure.
    """
    if not url:
        raise SSRFError("URL cannot be empty")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFError(f"Disallowed scheme: {scheme!r} (only http/https)")

    hostname = parsed.hostname or ""
    if not hostname:
        raise SSRFError("URL has no hostname")

    # Fast-path: block known-bad hostnames before DNS resolution
    if hostname in _BLOCKED_HOSTNAMES:
        raise SSRFError(f"Disallowed host: {hostname}")

    # Resolve hostname to IP and check against blocked networks
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except socket.gaierror:
        raise SSRFError(f"DNS resolution failed for: {hostname}")

    for family, _, _, _, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                raise SSRFError(
                    f"Host {hostname} resolves to private/metadata IP {ip} "
                    f"(blocked network: {net})"
                )

    return url
