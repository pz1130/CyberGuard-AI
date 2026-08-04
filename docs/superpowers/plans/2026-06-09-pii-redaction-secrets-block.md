# PII Redaction & Secrets Blocking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Standard's Data-Lineage & PII control (A5) — a pre-processing filter that **redacts PII** (SSN, credit card, passport, email) before *any* LLM call and **hard-blocks secrets** (API keys, passwords, tokens) so an agent never sends them to a model, with a redaction-proof audit record for the POC.

**Architecture:** A pure, DB-free `app/core/pii.py` module (detectors + redaction + Luhn) is the single source of truth. The `LLMRouter` gains one private `_guard_messages()` step invoked at all four `chat.completions.create()` sites (`parse_intent`, `generate_summary`, `chat`, `stream_chat`); it redacts per policy, raises `SecretsDetectedError` on secrets, and emits a proof record. Default policy is **redact, always-on** (every LLM call is protected); agent paths may override with their per-agent `pii_handling_policy`.

**Tech Stack:** Python `re`, FastAPI, OpenAI-compatible `AsyncOpenAI`, pytest/pytest-asyncio. No DB migration — code only.

---

## Dependencies & decisions

- **Optional dependency:** the redaction-proof record uses `record_action()` from the audit-hardening plan (`2026-06-09-agent-governance-controls.md`, Phase 1). The proof emission is **best-effort** (wrapped in try/except → falls back to `logger`), so this plan can land independently; if Phase 1 is present the proof is chained into the audit trail.
- **Per-agent policy** comes from the `pii_handling_policy` column added in the governance-config plan (`2026-06-09-governance-config-and-routing.md`). If that plan isn't landed, the global default applies and the per-agent override is simply unused — no breakage.
- **Policy semantics** (Standard §Data Lineage & PII):
  - `redact` (default): PII → `[REDACTED_<TYPE>]`; secrets → **block**.
  - `pseudonymize`: PII → stable token `[<TYPE>_<6hex>]`; secrets → **block**.
  - `block`: any PII **or** secret → block the call.
  - Secrets are **always blocked**, regardless of policy ("never read by agent").
- **Scope:** PII patterns are conservative (credit cards Luhn-validated) to limit false positives. Threat-intel/IOC text (IPs, hashes, domains) is **not** treated as PII — it passes unchanged (Standard: threat intel = allow).

## File Structure

| File | Responsibility |
|------|----------------|
| `app/core/pii.py` (create) | Pure detectors, `redact()`, `scan_secrets()`, `apply_policy()`, exceptions |
| `app/config.py` (modify) | `PII_FILTER_ENABLED`, `PII_HANDLING_POLICY` |
| `app/services/llm_router.py` (modify) | `_guard_messages()` + wire into the 4 create sites + proof record + `pii_policy` kwarg on `chat`/`stream_chat` |
| `app/services/internal_agent.py` (modify) | Pass the agent's `pii_handling_policy` to its router calls |
| `tests/test_pii.py` (create) | Pure detector/redaction/Luhn/policy tests |
| `tests/test_llm_router_pii.py` (create) | Wiring: redaction reaches `create()`, secrets raise |

---

### Task 1: Pure PII module

**Files:**
- Create: `app/core/pii.py`
- Test: `tests/test_pii.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pii.py
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
    valid = "card 4111 1111 1111 1111"          # passes Luhn
    invalid = "ticket 1234 5678 9012 3456"        # fails Luhn
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
    assert tokens[0] == tokens[2] and tokens[0] != tokens[1]   # same input → same token


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
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_pii.py -v
```
Expected: FAIL — `ModuleNotFoundError: app.core.pii`.

- [ ] **Step 3: Implement `app/core/pii.py`**

```python
"""PII redaction + secrets blocking (NDB Std §Data Lineage & PII / A5).

Pure, DB-free. redact() handles PII per policy; scan_secrets() detects
credentials that must NEVER reach an LLM. apply_policy() is the entry point the
LLM router calls before any completion.
"""
from __future__ import annotations
import hashlib
import re

# --- exceptions ------------------------------------------------------------
class PIIBlockedError(Exception):
    """Raised when policy=block and PII is present."""

class SecretsDetectedError(Exception):
    """Raised whenever a secret/credential is present (any policy)."""

# --- PII patterns (conservative) -------------------------------------------
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# 13–16 digit groups, optionally space/dash separated; Luhn-checked below.
_CC = re.compile(r"\b(?:\d[ -]?){13,16}\b")
# Passport: 1–2 letters + 6–9 digits (e.g. many national formats). Conservative.
_PASSPORT = re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")

# --- secret patterns -------------------------------------------------------
_SECRETS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                         # AWS access key id
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),                       # OpenAI-style key
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                      # GitHub PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),             # Slack token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),           # PEM private key
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
    return [{"type": "secret", "match": m.group(0)[:4] + "…"}
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
                return val  # not a real card → leave untouched
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
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_pii.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/pii.py tests/test_pii.py
git commit -m "feat(pii): pure PII redaction + secrets-block module (A5)"
```

### Task 2: Settings

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add to `Settings`**

```python
    PII_FILTER_ENABLED: bool = True
    PII_HANDLING_POLICY: str = "redact"   # redact | pseudonymize | block (global default)
```

- [ ] **Step 2: Commit**

```bash
git add app/config.py
git commit -m "feat(pii): PII_FILTER_ENABLED + default PII_HANDLING_POLICY settings"
```

### Task 3: Wire the guard into the LLM router

**Files:**
- Modify: `app/services/llm_router.py`
- Test: `tests/test_llm_router_pii.py`

- [ ] **Step 1: Write the failing tests** (mock `create()`; assert messages reach it redacted, and secrets raise)

```python
# tests/test_llm_router_pii.py
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services.llm_router import LLMRouter
from app.core.pii import SecretsDetectedError


def _resp(text="ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None),
                                 finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


@pytest.mark.asyncio
async def test_chat_redacts_pii_before_create():
    r = LLMRouter()
    captured = {}
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(side_effect=lambda **kw: captured.update(kw) or _resp()))))
    with patch.object(r, "get_client_async", AsyncMock(return_value=fake_client)), \
         patch.object(r, "_record_token_usage", AsyncMock()), \
         patch.object(r, "_load_master_config", AsyncMock(return_value={})), \
         patch("app.config.settings.MOCK_MODE", False):
        await r.chat([{"role": "user", "content": "email me at a@b.com"}], provider_id=1)
    sent = captured["messages"][-1]["content"]
    assert "a@b.com" not in sent and "[REDACTED_EMAIL]" in sent


@pytest.mark.asyncio
async def test_chat_blocks_secrets():
    r = LLMRouter()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_resp()))))
    with patch.object(r, "get_client_async", AsyncMock(return_value=fake_client)), \
         patch.object(r, "_load_master_config", AsyncMock(return_value={})), \
         patch("app.config.settings.MOCK_MODE", False):
        with pytest.raises(SecretsDetectedError):
            await r.chat([{"role": "user", "content": "use key AKIAIOSFODNN7EXAMPLE"}],
                         provider_id=1)
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_llm_router_pii.py -v
```
Expected: FAIL — email still present / no exception raised.

- [ ] **Step 3: Add the `_guard_messages` helper** to `LLMRouter` (place near `_strip_think_blocks`)

```python
    def _guard_messages(self, messages, pii_policy=None):
        """Redact PII + block secrets across all message contents (A5).

        Returns a NEW message list (originals untouched). Best-effort proof
        record; raises SecretsDetectedError/PIIBlockedError to abort the call.
        """
        from app.config import settings
        if not settings.PII_FILTER_ENABLED or not messages:
            return messages
        from app.core.pii import apply_policy
        policy = pii_policy or settings.PII_HANDLING_POLICY
        cleaned, total = [], 0
        for m in messages:
            content = m.get("content")
            if isinstance(content, str) and content:
                new_content, findings = apply_policy(content, policy=policy)
                total += len(findings)
                cleaned.append({**m, "content": new_content})
            else:
                cleaned.append(m)
        if total:
            self._emit_pii_proof(total, policy)
        return cleaned

    def _emit_pii_proof(self, count, policy):
        """POC proof: log redaction COUNT only — never the values."""
        try:
            import asyncio
            from app.core.audit import record_action
            asyncio.get_event_loop().create_task(record_action(
                user_id=None, action="pii_redaction", action_category="annotate",
                input_data={"policy": policy, "redactions": count},
                output_data={"redactions": count}))
        except Exception:
            import logging
            logging.getLogger("pii").info("pii_redaction policy=%s count=%d", policy, count)
```

- [ ] **Step 4: Add the `pii_policy` kwarg and call the guard in `chat()`**

Change the `chat` signature to add the kwarg:
```python
        tools: Optional[List[Dict[str, Any]]] = None,
        pii_policy: Optional[str] = None,
    ):
```
Insert immediately **before** `kwargs = {` (after the `client = await self.get_client_async(...)` line):
```python
            messages = self._guard_messages(messages, pii_policy)
```

- [ ] **Step 5: Do the same for `stream_chat()`** — add `pii_policy: Optional[str] = None` to its signature and insert before its `kwargs`/`create(` call:
```python
        messages = self._guard_messages(messages, pii_policy)
```

- [ ] **Step 6: Guard the two internal-prompt sites** — in `parse_intent()` (around line 601) and `generate_summary()` (around line 688), wrap the locally-built `messages` list right before the `create(` call:
```python
        messages = self._guard_messages(messages)
```

- [ ] **Step 7: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_llm_router_pii.py -v
```
Expected: both PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/llm_router.py tests/test_llm_router_pii.py
git commit -m "feat(pii): redact/secrets-block guard at all 4 LLM create() sites"
```

### Task 4: Per-agent policy override from governance config

**Files:**
- Modify: `app/services/internal_agent.py`

- [ ] **Step 1: Pass the agent's policy at the router calls.** At each `router.chat(...)` / `router.stream_chat(...)` call in `internal_agent.py` (≈ lines 520, 586, 829), add the kwarg sourced from the agent config:

```python
        pii_policy = self.config.get("pii_handling_policy")   # None → global default
        # e.g.:
        summary = await router.chat(messages=..., provider_id=..., pii_policy=pii_policy)
```

Apply to all three call sites (match each call's existing args; only add `pii_policy=pii_policy`).

- [ ] **Step 2: Run the internal-agent suite**

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/test_internal_agent.py -v
```
Expected: PASS (default policy is transparent for clean prompts).

- [ ] **Step 3: Commit**

```bash
git add app/services/internal_agent.py
git commit -m "feat(pii): agents pass per-agent pii_handling_policy to the LLM router"
```

**Plan gate:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/cyberguard \
  .venv/bin/python -m pytest tests/ -q
```
Expected: all pass.

---

## Self-Review notes (coverage vs the Standard)

- **A5 PII redaction before any LLM call** → Tasks 1–3: `apply_policy()` runs at all four `create()` sites; default `redact` is always-on, so even non-agent chat is protected.
- **A5 Secrets — never read by agent → block** → Task 1/3: `scan_secrets()` raises `SecretsDetectedError` regardless of policy, aborting the call before it reaches the model.
- **A5 "Proof required in POC"** → Task 3: `_emit_pii_proof()` records redaction **counts/policy only** (never values) into the audit trail (best-effort; chains into Phase-1 audit when present).
- **Per-agent `pii_handling_policy` (redact/pseudonymize/block)** → Task 4, sourced from the governance-config plan's column.
- **Threat-intel passes unchanged** → Task 1 test: IOCs/hashes/domains are not PII patterns.
- **Known limitations (call out at review):** regex detectors are best-effort — passport/credit-card patterns are conservative and will miss exotic formats; `_guard_messages` only filters string `content` (not tool-call argument payloads or structured multimodal parts) — extend to tool args in a follow-up if agents pass user data through tool calls. External non-LLM calls (tool-runner) are governed by the gatekeeper, not this filter; a dedicated egress-redaction pass for outbound tool args is a separate concern.
- **Still open for later plans (unchanged):** B6 Safety-Envelope rollback registry; `master.py` second-exec-path governance; POC evidence package + governance metrics; audit WORM export.
