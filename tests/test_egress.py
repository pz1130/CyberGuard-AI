"""Tests for the egress allowlist policy."""
import pytest
from app.core import egress
from app.core.ssrf import SSRFError


def test_disabled_passthrough_still_blocks_ssrf(monkeypatch):
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", False)
    with pytest.raises(SSRFError):
        egress.enforce_egress("http://169.254.169.254/latest/meta-data")
    assert egress.enforce_egress("https://example.com/x") == "https://example.com/x"


def test_allowlist_denies_unlisted(monkeypatch):
    monkeypatch.setattr(egress, "validate_outbound_url", lambda url: url)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "example.com")
    assert egress.enforce_egress("https://api.example.com/v3") == "https://api.example.com/v3"
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://evil.test/x")


def test_extra_allow_per_call(monkeypatch):
    monkeypatch.setattr(egress, "validate_outbound_url", lambda url: url)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "")
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://vt.example/x")
    assert egress.enforce_egress("https://vt.example/x", extra_allow=["vt.example"]) == "https://vt.example/x"


def test_exact_host_not_overmatched(monkeypatch):
    monkeypatch.setattr(egress, "validate_outbound_url", lambda url: url)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST_ENABLED", True)
    monkeypatch.setattr("app.config.settings.EGRESS_ALLOWLIST", "example.com")
    with pytest.raises(egress.EgressBlocked):
        egress.enforce_egress("https://notexample.com/x")
