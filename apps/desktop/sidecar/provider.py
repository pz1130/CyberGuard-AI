"""Desktop LLM provider config (M1.5 self-use).

Default remains **mock**. Live mode uses an OpenAI-compatible endpoint.

Config resolution order:
  1. Environment variables (highest priority for scripts/CI)
  2. ``{data_root}/provider.json`` (local self-use; mode 0600 recommended)
  3. mock

Env:
  CYBERGUARD_LLM_MODE=mock|live
  CYBERGUARD_LLM_BASE_URL=https://api.openai.com/v1
  CYBERGUARD_LLM_API_KEY=...
  CYBERGUARD_LLM_MODEL=gpt-4o-mini

provider.json example::

  {
    "mode": "live",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o-mini"
  }

API keys are never logged. M1.5 still forbids distribution of builds that
claim security properties (INV-38).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.desktop.sidecar.paths import data_root

logger = logging.getLogger("cyberguard.desktop.provider")


@dataclass(frozen=True)
class ProviderConfig:
    mode: str  # mock | live
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.3

    @property
    def is_live(self) -> bool:
        return self.mode == "live" and bool(self.api_key)

    def public_status(self) -> Dict[str, Any]:
        """Safe for UI / ping — never includes api_key."""
        return {
            "mode": "live" if self.is_live else "mock",
            "model": self.model if self.is_live else "mock",
            "base_url": self.base_url if self.is_live else None,
            "has_api_key": bool(self.api_key) if self.mode == "live" else False,
        }


def _load_file_config() -> Dict[str, Any]:
    path = data_root() / "provider.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to read provider.json: %s", type(exc).__name__)
        return {}


def load_provider_config() -> ProviderConfig:
    file_cfg = _load_file_config()
    mode = (
        os.environ.get("CYBERGUARD_LLM_MODE")
        or file_cfg.get("mode")
        or "mock"
    )
    mode = str(mode).strip().lower()
    if mode not in ("mock", "live"):
        mode = "mock"

    base_url = (
        os.environ.get("CYBERGUARD_LLM_BASE_URL")
        or file_cfg.get("base_url")
        or "https://api.openai.com/v1"
    )
    api_key = (
        os.environ.get("CYBERGUARD_LLM_API_KEY")
        or file_cfg.get("api_key")
        or ""
    )
    model = (
        os.environ.get("CYBERGUARD_LLM_MODEL")
        or file_cfg.get("model")
        or "gpt-4o-mini"
    )
    temp = file_cfg.get("temperature", 0.3)
    try:
        temperature = float(temp)
    except (TypeError, ValueError):
        temperature = 0.3

    cfg = ProviderConfig(
        mode=mode,
        base_url=str(base_url).rstrip("/"),
        api_key=str(api_key),
        model=str(model),
        temperature=temperature,
    )
    if mode == "live" and not cfg.api_key:
        logger.warning("LLM mode=live but no API key — falling back to mock")
        return ProviderConfig(mode="mock")
    return cfg


async def live_chat(
    cfg: ProviderConfig,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Any:
    """One chat completion via OpenAI-compatible API (AsyncOpenAI)."""
    from openai import AsyncOpenAI
    from llm_router.resilience import acall_with_retry
    from llm_router.utils import strip_think_blocks
    from types import SimpleNamespace

    client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    # Strip non-API fields from messages
    clean_msgs = []
    for m in messages:
        entry = {"role": m.get("role", "user"), "content": m.get("content")}
        if m.get("tool_calls"):
            entry["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
        clean_msgs.append(entry)

    kwargs: Dict[str, Any] = {
        "model": cfg.model,
        "messages": clean_msgs,
        "temperature": cfg.temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = await acall_with_retry(
        lambda: client.chat.completions.create(**kwargs),
        label="desktop_live_chat",
    )
    message = response.choices[0].message
    content = strip_think_blocks(message.content or "")
    if tools is not None:
        return SimpleNamespace(content=content, tool_calls=message.tool_calls)
    return content
