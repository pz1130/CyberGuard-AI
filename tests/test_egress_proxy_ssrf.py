"""The proxy's SSRF floor. An allowlisted name must not become a door inward."""
from __future__ import annotations

import pytest

from egress_proxy.ssrf import BlockedError, resolve_and_check


def test_rejects_metadata_hostnames_before_dns():
    for host in ("169.254.169.254", "metadata.google.internal", "localhost"):
        with pytest.raises(BlockedError):
            resolve_and_check(host)


def test_rejects_a_name_that_resolves_into_a_private_range(monkeypatch):
    # The whole point: the admin allowlisted vendor.example, but the attacker
    # controls that name and points it at the cloud metadata service.
    monkeypatch.setattr(
        "egress_proxy.ssrf._resolve", lambda h: "169.254.169.254")
    with pytest.raises(BlockedError, match="169.254.169.254"):
        resolve_and_check("vendor.example")


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.1.2.3", "172.16.0.5", "192.168.1.1", "0.0.0.0",
    "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1",
])
def test_rejects_every_blocked_range(monkeypatch, ip):
    monkeypatch.setattr("egress_proxy.ssrf._resolve", lambda h: ip)
    with pytest.raises(BlockedError):
        resolve_and_check("vendor.example")


def test_allows_a_public_address_and_returns_it(monkeypatch):
    monkeypatch.setattr("egress_proxy.ssrf._resolve", lambda h: "93.184.216.34")
    assert resolve_and_check("vendor.example") == "93.184.216.34"


def test_unresolvable_host_is_blocked_not_crashed(monkeypatch):
    def boom(_h):
        raise OSError("nodename nor servname provided")
    monkeypatch.setattr("egress_proxy.ssrf._resolve", boom)
    with pytest.raises(BlockedError):
        resolve_and_check("nope.invalid")
