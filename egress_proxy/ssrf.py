"""SSRF floor for the egress proxy.

Standalone by design: this package must not import from ``app`` (the rule
``tool_runner`` and ``skill_runner`` already follow), so the blocklist is
restated here. INV-41 asserts the two copies stay identical.
"""
from __future__ import annotations

import ipaddress
import socket

BLOCKED_NETWORKS = [
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

BLOCKED_HOSTNAMES = frozenset({
    "169.254.169.254",          # AWS / Azure metadata
    "metadata.google.internal",  # GCP metadata
    "metadata.internal",
    "metadata.azure.com",
    "localhost",
    "0.0.0.0",
    "127.0.0.1",
})


class BlockedError(Exception):
    """The destination is not one this proxy will open."""


def _resolve(host: str) -> str:
    """Resolve a hostname to a single IP string. Seam for tests."""
    return socket.getaddrinfo(host, None)[0][4][0]


def resolve_and_check(host: str) -> str:
    """Resolve *host* and return its IP, or raise BlockedError.

    The caller must connect to the returned IP rather than to the name.
    Resolving a second time would reopen the DNS-rebinding hole this closes.
    """
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        raise BlockedError("empty host")
    if name in BLOCKED_HOSTNAMES:
        raise BlockedError(f"host {name} is blocked")

    try:
        ip_text = _resolve(name)
    except OSError as e:
        raise BlockedError(f"cannot resolve {name}: {e}") from e

    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError as e:
        raise BlockedError(f"{name} resolved to an unusable address {ip_text!r}") from e

    for net in BLOCKED_NETWORKS:
        if ip.version == net.version and ip in net:
            raise BlockedError(
                f"host {name} resolves to private/metadata IP {ip_text}")
    return ip_text
