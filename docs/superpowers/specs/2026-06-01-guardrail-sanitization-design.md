# Guardrail Sanitization — Design

**Date:** 2026-06-01
**Status:** Approved (brainstorming)
**Area:** `app/core/guardrails.py`, `app/routers/chat.py`

## Problem

`GuardrailResult.sanitized` has always been `None` —
`app/core/guardrails.py` returns it as a hardcoded placeholder
(`sanitized=None,  # Future: implement sanitization pass`) in both
`check_prompt` (async) and `check_prompt_sync`. It is the only declared
feature in the platform with no implementation. No caller currently reads
the field.

## Goal

Implement a sanitization pass that produces a cleaned version of the user
input when the input contains **mechanical-noise** injection, and wire one
consumer (the canonical Master Agent chat entry) to actually use the cleaned
text instead of blocking when the risk is non-blocking but elevated.

## Non-goals

- Sanitizing pure **intent-based** jailbreaks (e.g. "ignore all previous
  instructions", "you are now a different AI"). Removing those leaves no
  meaningful prompt — these return `sanitized=None` and are handled by the
  existing block / risk-level logic.
- Wiring every guardrail call site. Only `POST /chat` is wired in this change.
  The other 5 sites (chat_stream, chat/attachments, agents execute ×2, worker)
  keep current behavior and can adopt the same one-liner later if wanted.

## Design

### 1. `sanitize_text(text: str) -> str` (new, in guardrails.py)

A set of **idempotent regex transforms** that neutralize only safely-fixable,
mechanical noise. Applied unconditionally and order-independently:

| Target (flag) | Transform |
|---|---|
| `recursive_injection` (`<system>`, `[SYSTEM]`, `<instruction>…`) | Strip the tags, keep inner text |
| `system_impersonation` (`system:`/`developer:`/`admin:` line prefix) | Drop the colon prefix |
| `html_tag_injection` | Strip HTML/XML tags, keep visible text |
| `markdown_link_injection` | `[text](url)` → `text` |
| `unicode_flood` / `escape_flood` | Collapse long runs to ≤ 3 repeats |
| `overlong_padding` (> 20 KB segment) | Truncate to the limit |
| `context_break_attempt` / `nested_delimiter_injection` | Remove the delimiter-injection substring |

**Left untouched:** code fences (commonly legitimate code), jailbreak intent
phrases, role-play prefixes.

### 2. Field-fill logic (shared by both entry points)

```
cleaned = sanitize_text(text)
sanitized = cleaned if cleaned != text else None
```

- Clean input → `cleaned == text` → `None`.
- Pure intent jailbreak (no mechanical transform fires) → `cleaned == text` → `None`.
- Mechanical noise present → cleaned text returned.

Refactor: extract the duplicated scoring / risk-level block that currently
exists in both `check_prompt` and `check_prompt_sync` into a shared helper so
the `sanitized` assignment lives in one place rather than being filled twice.

### 3. Consumer: `app/routers/chat.py` `POST /chat`

```
effective_input = body.message
if gr.sanitized and not gr.blocked and gr.risk_level in ("medium", "high"):
    effective_input = gr.sanitized
    logging.getLogger(__name__).warning(
        "[guardrail] substituted sanitized input user_id=%s risk=%s flags=%s",
        user_id, gr.risk_level, gr.flags,
    )
```

The Celery dispatch uses `effective_input`. **Conservative rule:** substitute
only for `medium`/`high` and not-blocked. `critical` is never substituted —
it routes through the existing block / audit-log path — which avoids the mixed
case where a message carries both mechanical noise and a real jailbreak intent
(stripping tags would not make it safe).

The execution record's stored `input_data.user_input` keeps the original raw
message for audit; only the value dispatched to the worker is the sanitized one.

### 4. Testing (`tests/test_integration.py::TestGuardrails`)

New cases against `check_prompt_sync`:

- HTML tags stripped: `<b>hi</b>` → `sanitized == "hi"`.
- `<system>…</system>` tags stripped, inner text retained.
- Emoji flood collapsed to ≤ 3 repeats; `sanitized` differs from input.
- Clean input → `sanitized is None`.
- Pure jailbreak (`Ignore all previous instructions…`) → `sanitized is None`.
- Re-checking a `sanitized` string does not itself score `critical` (the
  cleaned output is not a fresh injection).

## Risks / Mitigations

- **Sanitized text still risky (mixed jailbreak + noise):** consumer never
  substitutes on `critical`; only mechanical noise at medium/high is replaced.
- **Over-aggressive stripping changes legitimate meaning:** transforms target
  only injection-specific patterns; code fences and prose are left intact.
- **Double-fill drift between sync/async:** eliminated by the shared helper.
