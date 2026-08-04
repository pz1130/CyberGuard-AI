"""Prompt cache control helpers (M0a-2).

Stable system / skill content should be marked for provider prompt caching
when the wire format supports it.

* Anthropic Messages API (and some OpenAI-compat bridges): content blocks with
  ``cache_control: {"type": "ephemeral"}``.
* OpenAI automatic caching: no request field required for long identical
  prefixes; we optionally set ``prompt_cache_key`` when provided for routing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence


def _as_block_list(content: Any) -> List[Dict[str, Any]]:
    if isinstance(content, list):
        return [dict(c) if isinstance(c, Mapping) else {"type": "text", "text": str(c)} for c in content]
    return [{"type": "text", "text": str(content or "")}]


def mark_system_for_cache(
    messages: Sequence[Mapping[str, Any]],
    *,
    provider_type: Optional[str] = None,
    enabled: bool = True,
) -> List[Dict[str, Any]]:
    """Return a new message list; first system message marked for cache when enabled.

    Non-Anthropic providers: messages returned unchanged (OpenAI caches
    automatically by prefix). Anthropic-style: system content becomes a list
    of text blocks with cache_control on the last block.
    """
    if not enabled or not messages:
        return [dict(m) for m in messages]

    ptype = (provider_type or "").lower()
    # Only rewrite for Anthropic (or claude via compat that honors cache_control)
    use_blocks = ptype == "anthropic"

    out: List[Dict[str, Any]] = []
    marked = False
    for m in messages:
        msg = dict(m)
        if (
            use_blocks
            and not marked
            and msg.get("role") == "system"
            and msg.get("content") is not None
        ):
            blocks = _as_block_list(msg["content"])
            if blocks:
                last = dict(blocks[-1])
                last["cache_control"] = {"type": "ephemeral"}
                blocks[-1] = last
                msg["content"] = blocks
            marked = True
        out.append(msg)
    return out


def apply_prompt_cache_key(
    kwargs: Dict[str, Any],
    *,
    cache_key: Optional[str],
) -> Dict[str, Any]:
    """Attach prompt_cache_key for providers that support request-side keys."""
    out = dict(kwargs)
    if cache_key:
        out["prompt_cache_key"] = cache_key
    return out
