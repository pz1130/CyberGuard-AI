"""PII redaction + secrets blocking (NDB Std §Data Lineage & PII / A5).

Pure, DB-free. redact() handles PII per policy; scan_secrets() detects
credentials that must NEVER reach an LLM. apply_policy() is the entry point the
LLM router calls before any completion.
"""
from __future__ import annotations
import hashlib
import re


class PIIBlockedError(Exception):
    """Raised when policy=block and PII is present."""

class SecretsDetectedError(Exception):
    """Raised whenever a secret/credential is present (any policy)."""


_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_PASSPORT = re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")

_SECRETS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S{6,}"),
]


def _luhn_ok(digits: str) -> bool:
    d = [int(c) for c in digits if c.isdigit()]
    if not (13 <= len(d) <= 19):
        return False
    s, alt = 0, False
    for x in reversed(d):
        if alt:
            x *= 2
            if x > 9:
                x -= 9
        s += x
        alt = not alt
    return s % 10 == 0


def _token(kind: str, value: str) -> str:
    h = hashlib.sha256(value.encode()).hexdigest()[:6]
    return f"[{kind}_{h}]"


def scan_secrets(text: str) -> list[dict]:
    if not text:
        return []
    return [{"type": "secret", "match": m.group(0)[:4] + "\u2026"}
            for p in _SECRETS for m in p.finditer(text)]


def redact(text: str, policy: str = "redact") -> tuple[str, list[dict]]:
    """Return (possibly-redacted text, findings). Does NOT touch secrets."""
    if not text:
        return text, []
    findings: list[dict] = []

    def sub(pattern, kind, label, luhn=False):
        def _repl(m):
            val = m.group(0)
            if luhn and not _luhn_ok(val):
                return val
            findings.append({"type": kind})
            if policy == "pseudonymize":
                return _token(kind.upper(), val)
            return f"[REDACTED_{label}]"
        return pattern.sub(_repl, text)

    text = sub(_EMAIL, "email", "EMAIL")
    text = sub(_SSN, "ssn", "SSN")
    text = sub(_CC, "credit_card", "CREDIT_CARD", luhn=True)
    text = sub(_PASSPORT, "passport", "PASSPORT")
    return text, findings


def apply_policy(text: str, policy: str = "redact") -> tuple[str, list[dict]]:
    """Entry point. Always blocks secrets. Returns (clean_text, pii_findings)."""
    if scan_secrets(text):
        raise SecretsDetectedError("credential/secret detected; blocked before LLM")
    cleaned, findings = redact(text, policy=policy)
    if policy == "block" and findings:
        raise PIIBlockedError(f"PII present and policy=block ({len(findings)} findings)")
    return cleaned, findings
