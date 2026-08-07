"""Central prompt registry (audit #28).

Prompts previously lived as inline strings across seven modules, mixing
Chinese and English within a single request. This registry is the single
place to look up the *default* text for each role. Overrides from
master_config / per-conversation still win at the call site.
"""
from __future__ import annotations

from typing import Dict, Optional

_PROMPTS: Dict[str, str] = {
    "summarizer": (
        "You are CyberGuard's summarizer. Given sub-agent results, respond with "
        "a JSON object only (no markdown fence) of the form:\n"
        '{\n'
        '  "summary": "<concise English or Chinese summary matching the input language>",\n'
        '  "action_items": ["<concrete next step>", "..."],\n'
        '  "risk_score": <float 0.0-1.0>\n'
        "}\n"
        "Rules: one language per response (match the dominant language of the "
        "results); action_items must be concrete and operator-actionable; "
        "risk_score reflects residual operational risk, not confidence."
    ),
    "intent_parser_hint": (
        "You are CyberGuard's intent parser. Analyze user input and create a "
        "task plan. Output JSON only. Use one language per response."
    ),
    "chat_system_default": (
        "You are CyberGuard, a cybersecurity operations assistant. Be precise, "
        "cite tool outputs when relevant, and never invent scan results."
    ),
}


def get_prompt(name: str, default: Optional[str] = None) -> str:
    """Return a registered prompt by name, or *default* / empty string."""
    if name in _PROMPTS:
        return _PROMPTS[name]
    return default if default is not None else ""


def list_prompts() -> Dict[str, str]:
    return dict(_PROMPTS)


def register_prompt(name: str, text: str) -> None:
    """Override or add a prompt at runtime (tests / hot-config)."""
    _PROMPTS[name] = text
