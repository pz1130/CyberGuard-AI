"""Tests for PII redaction + secrets blocking."""
import pytest
from app.core import pii


def test_redacts_email_and_ssn():
    text = "contact john.doe@acme.com, SSN 123-45-6789 urgent"
    out, findings = pii.redact(text, policy="redact")
    assert "john.doe@acme.com" not in out and "[REDACTED_EMAIL]" in out
    assert "123-45-6789" not in out and "[REDACTED_SSN]" in out
    types = {f["type"] for f in findings}
    assert {"email", "ssn"} <= types


def test_redacts_valid_credit_card_only():
    valid = "card 4111 1111 1111 1111"
    invalid = "ticket 1234 5678 9012 3456"
    out_v, fv = pii.redact(valid, policy="redact")
    out_i, fi = pii.redact(invalid, policy="redact")
    assert "[REDACTED_CREDIT_CARD]" in out_v
    assert "[REDACTED_CREDIT_CARD]" not in out_i


def test_pseudonymize_is_stable_and_distinct():
    t = "a@x.com and b@x.com and a@x.com"
    out, _ = pii.redact(t, policy="pseudonymize")
    import re
    tokens = re.findall(r"\[EMAIL_[0-9a-f]{6}\]", out)
    assert len(tokens) == 3
    assert tokens[0] == tokens[2] and tokens[0] != tokens[1]


def test_scan_secrets_detects_keys():
    assert pii.scan_secrets("export AWS=AKIAIOSFODNN7EXAMPLE")
    assert pii.scan_secrets("authorization: Bearer sk-abcdef0123456789abcdef0123")
    assert pii.scan_secrets("password = hunter2longenough")
    assert pii.scan_secrets("-----BEGIN PRIVATE KEY-----")
    assert not pii.scan_secrets("the quick brown fox jumps over")


def test_threat_intel_passes_unchanged():
    t = "IOC 8.8.8.8 hash d41d8cd98f00b204e9800998ecf8427e domain evil.test"
    out, findings = pii.redact(t, policy="redact")
    assert out == t and findings == []


def test_apply_policy_block_raises_on_pii():
    with pytest.raises(pii.PIIBlockedError):
        pii.apply_policy("email a@b.com", policy="block")


def test_apply_policy_always_blocks_secrets():
    for policy in ("redact", "pseudonymize", "block"):
        with pytest.raises(pii.SecretsDetectedError):
            pii.apply_policy("key AKIAIOSFODNN7EXAMPLE", policy=policy)
