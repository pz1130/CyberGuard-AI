"""Message list helpers — exclude_from_context filtering (M0a-2).

Messages may carry ``exclude_from_context: true`` meaning:
  * still visible in UI / audit / persistence
  * **not** sent to the model

Evidence blobs, approval records, and policy_events belong here.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional


def mark_exclude_from_context(
    message: MutableMapping[str, Any],
    *,
    exclude: bool = True,
) -> MutableMapping[str, Any]:
    """Set / clear the flag in-place and return the message."""
    if exclude:
        message["exclude_from_context"] = True
    else:
        message.pop("exclude_from_context", None)
    return message


def is_excluded(message: Mapping[str, Any]) -> bool:
    return bool(message.get("exclude_from_context"))


def messages_for_model(
    messages: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Return a shallow-copied list suitable for the LLM (exclusions dropped).

    Does not mutate the original list or message dicts. Drops only the flag
    from copies is unnecessary — we omit whole messages.
    """
    out: List[Dict[str, Any]] = []
    for m in messages:
        if is_excluded(m):
            continue
        # Shallow copy so callers can safely mutate without touching storage
        out.append(dict(m))
    return out


def strip_exclude_flag(message: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy a message without the exclude flag (for display serialization)."""
    d = dict(message)
    d.pop("exclude_from_context", None)
    return d
