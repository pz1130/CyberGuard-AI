"""Pure helpers for LLM request/response shaping.

No I/O, no app/config, no agent concepts. Moved from ``app.services.llm_router``
in M0a-1 (behavior unchanged).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def model_name(model) -> Optional[str]:
    """Normalize a model reference to the bare model-name string the provider expects.

    A provider's ``models`` are stored as ``{"name": ..., "model_type": ...}`` dicts,
    and the UI may pass a model picked from that list as the whole object. The OpenAI
    client must receive just the name string, or the provider rejects the request with
    ``unknown model '{'name': ...}'``. Accepts str, dict, pydantic ModelInfo, or None.
    """
    if model is None or isinstance(model, str):
        return model
    if isinstance(model, dict):
        return model.get("name")
    return getattr(model, "name", None) or str(model)


def strip_think_blocks(text: str) -> str:
    """Remove provider-specific reasoning tags from visible output.

    <think>...</think> (and variants like <think>0, <think>_1) and
    <reasoning>...</reasoning> are always stripped — they are internal model
    chain-of-thought, never meant for the end user.
    """
    if not text:
        return text
    # Internal CoT blocks — always stripped regardless of preserve_think.
    # Multiple tag variants observed across providers (MiniMax M3, Qwen3,
    # DeepSeek, etc.): <think>, <think>0, <think>_1, <think>abc; and
    # <reasoning>...</reasoning>.
    text = re.sub(
        r"<think[^>]*>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"<reasoning>[\s\S]*?</reasoning>\s*", "", text, flags=re.IGNORECASE
    )
    return text.strip()


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract and parse the first balanced top-level JSON object from text.

    Handles provider outputs like: <think>...</think>{...json...}
    """
    cleaned = strip_think_blocks(text)

    # Fast path: pure JSON
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Balanced-brace scan
    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                try:
                    data = json.loads(candidate)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    return None
    return None
