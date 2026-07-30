"""Unified thinking / reasoning effort levels (M0a-2).

Callers pass a portable level; we map to provider-specific request fields.

Levels: off | minimal | low | medium | high | xhigh
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]

_VALID = frozenset({"off", "minimal", "low", "medium", "high", "xhigh"})

# OpenAI o-series / reasoning models: reasoning_effort
_OPENAI_EFFORT = {
    "off": None,  # omit field
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
}

# Anthropic extended thinking budget tokens (approx)
_ANTHROPIC_BUDGET = {
    "off": None,
    "minimal": 1024,
    "low": 2048,
    "medium": 8192,
    "high": 16384,
    "xhigh": 32768,
}


def normalize_thinking_level(level: Optional[str]) -> Optional[ThinkingLevel]:
    if level is None:
        return None
    v = str(level).strip().lower()
    if v in _VALID:
        return v  # type: ignore[return-value]
    return None


def _looks_openai_reasoning(model: str) -> bool:
    m = model.lower()
    return m.startswith("o1") or m.startswith("o3") or m.startswith("o4") or "reasoner" in m


def apply_thinking_to_kwargs(
    kwargs: Dict[str, Any],
    *,
    level: Optional[str],
    model: str,
    provider_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Mutate a copy of chat-completion kwargs with provider-specific thinking.

    Returns a new dict. Unknown providers / levels → kwargs unchanged.
    """
    out = dict(kwargs)
    lvl = normalize_thinking_level(level)
    if lvl is None or lvl == "off":
        return out

    ptype = (provider_type or "").lower()
    model_l = (model or "").lower()

    # OpenAI-compatible reasoning
    if ptype in ("openai", "azure", "custom", "xai", "deepseek", "") or _looks_openai_reasoning(
        model_l
    ):
        if _looks_openai_reasoning(model_l) or "deepseek-reasoner" in model_l:
            effort = _OPENAI_EFFORT.get(lvl)
            if effort:
                # Newer SDKs accept reasoning_effort; some gateways use extra_body
                out["reasoning_effort"] = effort
            return out

    # Anthropic (when using OpenAI-compat bridge that accepts thinking)
    if ptype == "anthropic" or "claude" in model_l:
        budget = _ANTHROPIC_BUDGET.get(lvl)
        if budget:
            # Common OpenAI-compat mapping for Claude thinking
            extra = dict(out.get("extra_body") or {})
            extra["thinking"] = {"type": "enabled", "budget_tokens": budget}
            out["extra_body"] = extra
        return out

    # Generic: stash under extra_body for gateways that understand it
    extra = dict(out.get("extra_body") or {})
    extra["thinking_level"] = lvl
    out["extra_body"] = extra
    return out
