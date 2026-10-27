"""
Prompt injection screening for typed user input.

Rule-based only — there is no model-based classifier. Strategies:
  1. Direct injection pattern matching (overlong, repeated escapes, etc.)
  2. Markup/tag injection (HTML, XML, markdown bracket injection)
  3. Soft-rejected injection (system prompt impersonation, role-play attempts)
  4. Structural anomaly scoring (entropy + repetition flags)

Critical risk is always blocked; medium and high pass through flagged unless
block=True. Callers screen only the text a user types: attachment text,
knowledge-base context, conversation history and tool/MCP output are added
later and are never screened. See docs/delivery/ARCHITECTURE_AND_SECURITY.md.
"""

from __future__ import annotations

import math
import re
import os
from dataclasses import dataclass
from typing import Literal

# ----------------------------------------------------------------------
# Result types
# ----------------------------------------------------------------------


@dataclass
class GuardrailResult:
    passed: bool          # False if injection detected
    blocked: bool          # True if the input should be hard-rejected
    risk_level: Literal["low", "medium", "high", "critical"]
    score: float           # 0.0 (clean) → 1.0 (clearly malicious)
    flags: list[str]        # Human-readable names of triggered rules
    message: str           # Short human-readable summary
    sanitized: str | None  # Suggested sanitized version (if fixable)


# ----------------------------------------------------------------------
# Strategy 1: Direct injection patterns
# ----------------------------------------------------------------------
#
# These patterns catch unambiguous injection attempts — content that
# could cause the model to ignore its system instructions.

_INJECTION_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Overlong padding designed to overwhelm context windows or dilute instructions
    (
        "overlong_padding",
        re.compile(
            r'(.{20000,})',  # any single token/segment > 20 kB
            re.DOTALL,
        ),
        "Input contains an excessively long segment (> 20 KB)",
    ),
    # Emoji/unicode garbage padding
    (
        "unicode_flood",
        re.compile(
            r'([\U0001F600-\U0001F64F\u2600-\u26FF\u2700-\u27BF])\1{19,}',
            # any emoji char repeated 20+ times
        ),
        "Input contains repeated unicode characters (possible flood attack)",
    ),
    # Repetitive escape sequences
    (
        "escape_flood",
        re.compile(r'(\\n|\\t|\\r|\\\\){30,}', re.UNICODE),
        "Input contains a flood of escape sequences",
    ),
    # Attempt to close the outer context and inject new context
    (
        "context_break_attempt",
        re.compile(
            r'"""\s*\}|\'\'\'\s*\}|\}\s*"""',
            re.DOTALL,
        ),
        "Input contains a structural context-break pattern",
    ),
    # Direct instruction override attempts
    (
        "direct_instruction_override",
        re.compile(
            r'^(ignore|forget|disregard|discard)\s+(all?\s+)?(previous|prior|above|'
            r'instructions?|rules?|guidelines?|system)\b',
            re.IGNORECASE,
        ),
        "Input contains a direct instruction-override attempt",
    ),
    # "You are now a different system" jailbreak prefix
    (
        "jailbreak_prefix",
        re.compile(
            r'^(you\s+are\s+now|pretend\s+you\s+are|switch\s+to\s+being|'
            r'act\s+as\s+if\s+you\s+are|imagine\s+you\s+are|'
            r'disregard\s+.*?\s+and\s+be|forget.*?and\s+become)\b',
            re.IGNORECASE,
        ),
        "Input begins with a jailbreak role-play attempt",
    ),
    # Recursive prompt injection (user wrapping their input as system-level)
    (
        "recursive_injection",
        re.compile(
            r'<\s*system\s*>|<\s*/\s*system\s*>|'
            r'<\s*system_prompt\s*>|<\s*/\s*system_prompt\s*>|'
            r'\[\s*SYSTEM\s*\]|\[\s*/\s*SYSTEM\s*\]|'
            r'\{\s*system\s*:|'
            r'<\s*instruction\s*>.*?<\s*/\s*instruction\s*>',
            re.IGNORECASE | re.DOTALL,
        ),
        "Input contains what appears to be a system-prompt injection tag",
    ),
]


def _check_injection_patterns(text: str) -> tuple[list[str], list[str]]:
    """
    Run all direct injection patterns.
    Returns (triggered_rule_names, trigger_messages).
    """
    triggered: list[str] = []
    messages: list[str] = []
    for name, pattern, msg in _INJECTION_PATTERNS:
        if pattern.search(text):
            triggered.append(name)
            messages.append(msg)
    return triggered, messages


# ----------------------------------------------------------------------
# Strategy 2: Markup / tag injection
# ----------------------------------------------------------------------


_MARKUP_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # HTML / XML tags
    (
        "html_tag_injection",
        re.compile(r'<[a-zA-Z][^>]*>.*?</[a-zA-Z][^>]*>', re.DOTALL | re.IGNORECASE),
        "Input contains HTML/XML tags",
    ),
    # Markdown image/link injection (used to hide URIs)
    (
        "markdown_link_injection",
        re.compile(r'!?\[([^\]]+)\]\(([^\)]+)\)', re.UNICODE),
        "Input contains markdown link syntax",
    ),
    # Backtick/code fence injection
    (
        "code_fence_injection",
        re.compile(r'^```[\w*+-]*\s*\n[\s\S]+?\n```', re.MULTILINE),
        "Input contains a code-fence block",
    ),
]


def _check_markup_patterns(text: str) -> tuple[list[str], list[str]]:
    triggered = []
    messages = []
    for name, pattern, msg in _MARKUP_PATTERNS:
        if pattern.search(text):
            triggered.append(name)
            messages.append(msg)
    return triggered, messages


# ---------------------------------------------------------------------------
# Strategy 3: Soft-rejected patterns (patterns cannot be certain here,
# but we can flag clearly suspicious content)
# ---------------------------------------------------------------------------


_SOFT_REJECT_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Attempts to impersonate system / developer messages
    (
        "system_impersonation",
        re.compile(
            r'^(system|developer|admin)\s*:\s*',
            re.IGNORECASE | re.MULTILINE,
        ),
        "Input contains what looks like a system/developer impersonation attempt",
    ),
    # Role-play prefix appended to user messages
    (
        "role_play_attempt",
        re.compile(
            r'^(you\s+are\s+|you\s+act\s+as\s+|as\s+a\s+|as\s+an\s+)',
            re.IGNORECASE,
        ),
        "Input begins with a role-play directive",
    ),
    # Nested delimiter injection (attempting to close off the real prompt)
    (
        "nested_delimiter_injection",
        re.compile(r'"""\s*\{|\'\'\'\s*\{|\}\s*"""'),
        "Input contains nested delimiter injection",
    ),
]


def _check_soft_reject_patterns(text: str) -> tuple[list[str], list[str]]:
    triggered = []
    messages = []
    for name, pattern, msg in _SOFT_REJECT_PATTERNS:
        if pattern.search(text):
            triggered.append(name)
            messages.append(msg)
    return triggered, messages


# ---------------------------------------------------------------------------
# Strategy 4: Structural anomaly scoring
# ---------------------------------------------------------------------------


def _shannon_entropy(text: str) -> float:
    """Calculate per-character Shannon entropy of a string."""
    if not text:
        return 0.0
    import collections
    freq = collections.Counter(text)
    length = len(text)
    entropy = 0.0
    for count in freq.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def _score_structural_anomaly(text: str) -> dict:
    """
    Score structural anomalies that may indicate obfuscated injection.
    Returns a dict with flags and an overall structural score 0-1.
    """
    flags = []
    score = 0.0

    # High entropy (many distinct characters) could indicate encoded/obfuscated content
    entropy = _shannon_entropy(text)
    if entropy > 6.5:
        flags.append("very_high_entropy")
        score += 0.25
    elif entropy > 5.5:
        flags.append("elevated_entropy")
        score += 0.1

    # Check for unusual ratio of non-printable / control characters
    control_ratio = sum(1 for c in text if ord(c) < 32 and c not in "\n\t\r") / max(len(text), 1)
    if control_ratio > 0.05:
        flags.append("excessive_control_chars")
        score += 0.3

    # Repetitive substring ratio — very high repetition may indicate templates
    # Simple heuristic: if the same 3-char substring appears > 30% of text length
    if len(text) >= 20:
        import collections
        substr3 = [text[i:i + 3] for i in range(len(text) - 2)]
        if substr3:
            most_common_count = collections.Counter(substr3).most_common(1)[0][1]
            repetition_ratio = most_common_count / len(substr3)
            if repetition_ratio > 0.30:
                flags.append("high_repetition")
                score += 0.2

    # Very short inputs can't be meaningfully analyzed structurally
    if len(text) < 10:
        score = 0.0

    # Cap score
    score = min(score, 1.0)
    return {"flags": flags, "score": score}


# ----------------------------------------------------------------------
# Sanitization pass — neutralize mechanical-noise injection only
# ----------------------------------------------------------------------

_MAX_SEGMENT = 20000  # overlong_padding flags segments >= this; we cap length here

# Tag/markup strippers (keep inner visible text)
_RE_SYSTEM_TAGS = re.compile(
    r'<\s*/?\s*(system|system_prompt|instruction)\s*>',
    re.IGNORECASE,
)
_RE_BRACKET_SYSTEM = re.compile(r'\[\s*/?\s*SYSTEM\s*\]', re.IGNORECASE)
_RE_HTML_TAG = re.compile(r'<[a-zA-Z][^>]*>|</[a-zA-Z][^>]*>')
_RE_IMPERSONATION = re.compile(
    r'^(system|developer|admin)\s*:\s*',
    re.IGNORECASE | re.MULTILINE,
)
_RE_MD_LINK = re.compile(r'!?\[([^\]]+)\]\([^\)]+\)')
# Flood thresholds here (collapse at 4+) are deliberately lower/more aggressive
# than the detection rules in _INJECTION_PATTERNS (which only FLAG at 20+/30+):
# sanitization neutralizes noise the detector may not even flag.
_RE_EMOJI_FLOOD = re.compile(
    r'([\U0001F300-\U0001FAFF☀-➿])\1{3,}'
)
_RE_ESCAPE_FLOOD = re.compile(r'(\\n|\\t|\\r|\\\\)\1{3,}')
_RE_DELIMITER_INJECTION = re.compile(
    r'"""\s*[{}]|\'\'\'\s*[{}]|[{}]\s*"""'
)


def sanitize_text(text: str) -> str:
    """
    Produce a cleaned version of `text` with mechanical-noise injection
    neutralized. Idempotent: running it on already-clean text returns the
    text unchanged. Pure-intent jailbreaks (no mechanical noise) are left
    unchanged — they are not safely fixable and the caller handles them via
    risk-level / blocking.
    """
    if not text:
        return text
    out = text

    # Truncate any overlong segment first (cheapest way to bound the rest)
    if len(out) > _MAX_SEGMENT:
        out = out[:_MAX_SEGMENT]

    # Apply every neutralizing transform to a fixed point. One pass can expose
    # input for another (e.g. stripping a tag reveals a `system:` prefix, or an
    # outer markdown link reveals an inner one), so we loop until the string
    # stops changing. Tags/markers are replaced with a space so adjacent words
    # don't fuse; whitespace is then collapsed. Every transform only shortens
    # (or leaves unchanged) the string, so the loop always terminates, and the
    # result is idempotent: re-running sanitize_text on its own output is a no-op.
    prev = None
    while prev != out:
        prev = out
        # Strip system/instruction tags, bracket-system markers, HTML/XML tags
        out = _RE_SYSTEM_TAGS.sub(" ", out)
        out = _RE_BRACKET_SYSTEM.sub(" ", out)
        out = _RE_HTML_TAG.sub(" ", out)
        # Drop system/developer/admin impersonation prefixes
        out = _RE_IMPERSONATION.sub("", out)
        # Markdown links -> just the link text
        out = _RE_MD_LINK.sub(r"\1", out)
        # Collapse unicode / escape floods to a single repeat
        out = _RE_EMOJI_FLOOD.sub(r"\1", out)
        out = _RE_ESCAPE_FLOOD.sub(r"\1", out)
        # Remove delimiter-injection substrings
        out = _RE_DELIMITER_INJECTION.sub("", out)
        # Collapse the whitespace that stripping may have left; trim the ends
        out = re.sub(r"[ \t]{2,}", " ", out).strip()

    return out


def pick_effective_input(raw: str, result: "GuardrailResult") -> str:
    """
    Decide which text to forward to the downstream agent.

    Returns the sanitized version only when it exists, the input was not
    blocked, and the risk is elevated-but-recoverable (medium/high). For
    `critical` (or when nothing was sanitized) the raw input is returned —
    critical inputs route through the existing block / audit path instead.
    """
    if (
        result.sanitized
        and not result.blocked
        and result.risk_level in ("medium", "high")
    ):
        return result.sanitized
    return raw


_CRITICAL_FLAGS = frozenset({
    "jailbreak_prefix",
    "recursive_injection",
    "direct_instruction_override",
})


def _escalate_critical_flags(flags: list[str], risk_level: str) -> str:
    if any(f in _CRITICAL_FLAGS for f in flags):
        return "critical"
    return risk_level


def _pass_block(risk_level: str, *, block: bool) -> tuple[bool, bool]:
    """Critical injection is always hard-blocked. `block=True` also rejects high."""
    blocked = risk_level == "critical" or (block and risk_level in ("high", "critical"))
    passed = not blocked and risk_level in ("low", "medium", "high")
    return passed, blocked


# ----------------------------------------------------------------------
# Main guardrail function
# ----------------------------------------------------------------------


def check_prompt_sync(text: str, *, block: bool = False) -> GuardrailResult:
    """
    Run all rule-based strategies against a user prompt.

    Args:
        text:  The raw user input string.
        block: If True, also hard-reject high risk. Critical is always blocked.
    """
    p_flags, p_msgs = _check_injection_patterns(text)
    m_flags, m_msgs = _check_markup_patterns(text)
    s_flags, s_msgs = _check_soft_reject_patterns(text)
    struct = _score_structural_anomaly(text)

    flags = p_flags + m_flags + s_flags + struct["flags"]
    messages = p_msgs + m_msgs + s_msgs

    direct_score = len(p_flags) * 0.35
    markup_score = len(m_flags) * 0.2
    soft_score = len(s_flags) * 0.15
    total_score = min(direct_score + markup_score + soft_score + struct["score"], 1.0)

    if total_score >= 0.7 or "jailbreak_prefix" in flags or "recursive_injection" in flags:
        risk_level: Literal["low", "medium", "high", "critical"] = "critical"
    elif total_score >= 0.45 or len(flags) >= 3:
        risk_level = "high"
    elif total_score >= 0.2 or flags:
        risk_level = "medium"
    else:
        risk_level = "low"
    risk_level = _escalate_critical_flags(flags, risk_level)

    passed, blocked = _pass_block(risk_level, block=block)

    message = f"Detected {len(flags)} signal(s): {', '.join(flags[:5])}" if flags else "No injection signals detected"

    cleaned = sanitize_text(text)
    return GuardrailResult(
        passed=passed,
        blocked=blocked,
        risk_level=risk_level,
        score=round(total_score, 3),
        flags=flags,
        message=message,
        sanitized=cleaned if cleaned != text else None,
    )
