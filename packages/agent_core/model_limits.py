"""Per-model context_window / max_output_tokens catalog and resolution (M0a-2).

Values are best-effort defaults for known model name patterns. Callers may
override by storing explicit fields on provider.models[] entries.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Safe defaults when nothing is known (generous modern chat model).
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 4_096

# (substring_or_regex, context_window, max_output_tokens) — first match wins.
# Order: more specific patterns first.
_CATALOG: List[Tuple[str, int, int]] = [
    # OpenAI
    (r"^gpt-4o-mini", 128_000, 16_384),
    (r"^gpt-4o", 128_000, 16_384),
    (r"^gpt-4-turbo", 128_000, 4_096),
    (r"^gpt-4\.1", 1_047_576, 32_768),
    (r"^gpt-4", 8_192, 4_096),
    (r"^gpt-3\.5", 16_385, 4_096),
    (r"^o1", 200_000, 100_000),
    (r"^o3", 200_000, 100_000),
    # Anthropic
    (r"claude-.*opus", 200_000, 32_000),
    (r"claude-.*sonnet", 200_000, 64_000),
    (r"claude-.*haiku", 200_000, 8_192),
    (r"claude-", 200_000, 8_192),
    # Google
    (r"gemini-2\.5", 1_048_576, 65_536),
    (r"gemini-2\.0", 1_048_576, 8_192),
    (r"gemini-", 1_048_576, 8_192),
    # DeepSeek / Qwen / Moonshot / xAI / MiniMax
    (r"deepseek", 64_000, 8_192),
    (r"qwen-long", 1_000_000, 8_192),
    (r"qwen", 128_000, 8_192),
    (r"kimi|moonshot", 128_000, 8_192),
    (r"grok-", 131_072, 8_192),
    (r"minimax", 1_000_000, 8_192),
    # Llama / local-ish
    (r"llama-3\.3|llama3\.3", 128_000, 8_192),
    (r"llama-3\.1|llama3\.1", 128_000, 8_192),
    (r"llama", 32_768, 4_096),
    (r"mixtral", 32_768, 4_096),
]


def lookup_model_limits(model_name: Optional[str]) -> Tuple[int, int]:
    """Return ``(context_window, max_output_tokens)`` from the static catalog."""
    if not model_name:
        return DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS
    name = str(model_name).strip().lower()
    # strip provider prefixes like "openai/gpt-4o"
    if "/" in name:
        name = name.split("/")[-1]
    for pattern, cw, mo in _CATALOG:
        if re.search(pattern, name, re.IGNORECASE):
            return cw, mo
    return DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS


def _entry_name(entry: Any) -> Optional[str]:
    if isinstance(entry, Mapping):
        return entry.get("name")
    return getattr(entry, "name", None) or (str(entry) if entry else None)


def resolve_model_limits(
    model_name: Optional[str],
    models: Optional[List[Any]] = None,
) -> Tuple[int, int]:
    """Prefer explicit fields on a stored model entry, else catalog, else defaults.

    ``models`` is the provider's models JSON list (dicts or ModelInfo-like).
    """
    if models and model_name:
        for m in models:
            if _entry_name(m) == model_name:
                cw = None
                mo = None
                if isinstance(m, Mapping):
                    cw = m.get("context_window")
                    mo = m.get("max_output_tokens")
                else:
                    cw = getattr(m, "context_window", None)
                    mo = getattr(m, "max_output_tokens", None)
                cat_cw, cat_mo = lookup_model_limits(model_name)
                return (
                    int(cw) if cw else cat_cw,
                    int(mo) if mo else cat_mo,
                )
    return lookup_model_limits(model_name)


def enrich_model_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Fill context_window / max_output_tokens when missing (non-destructive)."""
    out = dict(entry)
    name = out.get("name")
    cat_cw, cat_mo = lookup_model_limits(name)
    if not out.get("context_window"):
        out["context_window"] = cat_cw
    if not out.get("max_output_tokens"):
        out["max_output_tokens"] = cat_mo
    return out


def enrich_models_list(models: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Normalize a models list and enrich each chat model entry."""
    result: List[Dict[str, Any]] = []
    for m in models or []:
        if isinstance(m, Mapping):
            entry = dict(m)
        else:
            entry = {"name": str(m), "model_type": "chat"}
        if entry.get("model_type", "chat") == "chat":
            entry = enrich_model_entry(entry)
        result.append(entry)
    return result
