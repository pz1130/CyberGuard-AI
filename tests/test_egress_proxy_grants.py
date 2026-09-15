"""Per-execution grants and hostname matching."""
from __future__ import annotations

import pytest

from egress_proxy.grants import GrantStore, host_allowed


@pytest.mark.parametrize("host,allowed", [
    ("vendor.example", True),
    ("VENDOR.EXAMPLE", True),          # case-insensitive
    ("vendor.example.", True),         # trailing dot
    ("api.vendor.example", False),     # exact entry does not cover subdomains
    ("evilvendor.example", False),     # not a suffix match on a label boundary
    ("other.example", False),
])
def test_exact_entries_match_only_that_host(host, allowed):
    assert host_allowed(host, ["vendor.example"]) is allowed


@pytest.mark.parametrize("host,allowed", [
    ("api.vendor.example", True),
    ("deep.api.vendor.example", True),
    ("vendor.example", True),          # the bare domain is covered too
    ("evilvendor.example", False),     # must not match without the dot
    ("vendor.example.evil.com", False),
])
def test_dot_prefixed_entries_match_the_suffix(host, allowed):
    assert host_allowed(host, [".vendor.example"]) is allowed


def test_empty_allowlist_permits_nothing():
    assert host_allowed("vendor.example", []) is False


def test_grant_lookup_and_revoke():
    store = GrantStore()
    store.grant("n1", ["vendor.example"], ttl=60)
    assert store.lookup("n1") == ["vendor.example"]
    store.revoke("n1")
    assert store.lookup("n1") is None


def test_unknown_nonce_is_none():
    assert GrantStore().lookup("never-granted") is None


def test_expired_grant_is_none():
    clock = {"t": 1000.0}
    store = GrantStore(now=lambda: clock["t"])
    store.grant("n1", ["vendor.example"], ttl=30)
    clock["t"] = 1029.0
    assert store.lookup("n1") == ["vendor.example"]
    clock["t"] = 1031.0
    assert store.lookup("n1") is None


def test_purge_drops_expired_entries():
    clock = {"t": 0.0}
    store = GrantStore(now=lambda: clock["t"])
    store.grant("a", ["x.example"], ttl=10)
    store.grant("b", ["y.example"], ttl=100)
    clock["t"] = 50.0
    store.purge()
    assert store.lookup("a") is None
    assert store.lookup("b") == ["y.example"]


def test_one_nonce_cannot_see_another_nonces_hosts():
    store = GrantStore()
    store.grant("n1", ["a.example"], ttl=60)
    store.grant("n2", ["b.example"], ttl=60)
    assert host_allowed("b.example", store.lookup("n1")) is False
    assert host_allowed("a.example", store.lookup("n2")) is False
