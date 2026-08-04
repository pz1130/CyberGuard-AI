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
    # Prefer env, then Keychain/secrets store (M3), then provider.json (legacy)
    api_key = os.environ.get("CYBERGUARD_LLM_API_KEY") or ""
    if not api_key:
        try:
            from apps.desktop.sidecar.secrets_store import get_provider_api_key

            api_key = get_provider_api_key() or ""
        except Exception:  # noqa: BLE001
            api_key = ""
    if not api_key:
        api_key = str(file_cfg.get("api_key") or "")
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


def get_provider_public() -> Dict[str, Any]:
    """Settings-safe provider view — never includes api_key."""
    file_cfg = _load_file_config()
    mode = str(file_cfg.get("mode") or "mock").strip().lower()
    if mode not in ("mock", "live"):
        mode = "mock"
    base_url = str(
        file_cfg.get("base_url") or "https://api.openai.com/v1"
    ).rstrip("/")
    model = str(file_cfg.get("model") or "gpt-4o-mini")
    try:
        temperature = float(file_cfg.get("temperature", 0.3))
    except (TypeError, ValueError):
        temperature = 0.3

    has_key = False
    try:
        from apps.desktop.sidecar.secrets_store import get_provider_api_key

        has_key = bool(get_provider_api_key())
    except Exception:  # noqa: BLE001
        has_key = False
    if not has_key:
        has_key = bool(file_cfg.get("api_key"))

    # Effective runtime (env may override)
    effective = load_provider_config().public_status()
    return {
        "mode": mode,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        "has_api_key": has_key,
        "effective": effective,
    }


def set_provider_config(params: Dict[str, Any]) -> Dict[str, Any]:
    """Persist public fields; move api_key to secrets store when provided."""
    file_cfg = _load_file_config()
    mode = str(params.get("mode") if params.get("mode") is not None else file_cfg.get("mode") or "mock")
    mode = mode.strip().lower()
    if mode not in ("mock", "live"):
        mode = "mock"

    base_url = str(
        params.get("base_url")
        if params.get("base_url") is not None
        else file_cfg.get("base_url")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = str(
        params.get("model")
        if params.get("model") is not None
        else file_cfg.get("model")
        or "gpt-4o-mini"
    )
    temp_in = params.get("temperature")
    if temp_in is None:
        temp_in = file_cfg.get("temperature", 0.3)
    try:
        temperature = float(temp_in)
    except (TypeError, ValueError):
        temperature = 0.3

    api_key = params.get("api_key")
    if api_key is not None and str(api_key).strip():
        from apps.desktop.sidecar.secrets_store import set_provider_api_key

        set_provider_api_key(str(api_key).strip())

    out: Dict[str, Any] = {
        "mode": mode,
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
        # never persist key in file
        "api_key_in_keychain": True,
    }
    path = data_root() / "provider.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

    return get_provider_public() | {"ok": True}


async def test_provider_connection() -> Dict[str, Any]:
    """Cheap connectivity check for Settings → Test."""
    import time

    cfg = load_provider_config()
    t0 = time.perf_counter()
    if not cfg.is_live:
        return {
            "ok": True,
            "mode": "mock",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "message": "mock mode — no network call",
        }
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        # Minimal completion — 1 token style prompt
        await client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return {
            "ok": True,
            "mode": "live",
            "model": cfg.model,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "mode": "live",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}"[:400],
        }


async def live_chat(
    cfg: ProviderConfig,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    *,
    on_delta: Optional[Any] = None,
) -> Any:
    """One chat completion via OpenAI-compatible API (AsyncOpenAI).

    When ``tools`` is None/empty and ``on_delta`` is provided, uses streaming
    and invokes ``await on_delta(chunk: str)`` for each content delta so the UI
    can show tokens as they arrive.
    """
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
    use_tools = bool(tools)
    if use_tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # Streaming path — emit content deltas for UI; assemble tool_calls if any.
    if on_delta is not None:
        stream = await client.chat.completions.create(**kwargs, stream=True)
        parts: List[str] = []
        # index -> accumulated tool call pieces
        tc_acc: Dict[int, Dict[str, Any]] = {}
        async for chunk in stream:
            try:
                choice = chunk.choices[0] if chunk.choices else None
                delta = getattr(choice, "delta", None) if choice else None
            except Exception:  # noqa: BLE001
                delta = None
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                parts.append(piece)
                try:
                    maybe = on_delta(piece)
                    if hasattr(maybe, "__await__"):
                        await maybe
                except Exception:  # noqa: BLE001
                    pass
            tcs = getattr(delta, "tool_calls", None) or []
            for tc in tcs:
                try:
                    idx = int(getattr(tc, "index", 0) or 0)
                except Exception:  # noqa: BLE001
                    idx = 0
                slot = tc_acc.setdefault(
                    idx, {"id": "", "name": "", "arguments": ""}
                )
                if getattr(tc, "id", None):
                    slot["id"] = str(tc.id)
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = str(fn.name)
                    if getattr(fn, "arguments", None):
                        slot["arguments"] = slot["arguments"] + str(fn.arguments)
        content = strip_think_blocks("".join(parts))
        if tc_acc:
            built = []
            for i in sorted(tc_acc.keys()):
                slot = tc_acc[i]
                built.append(
                    SimpleNamespace(
                        id=slot["id"] or f"call_{i}",
                        function=SimpleNamespace(
                            name=slot["name"],
                            arguments=slot["arguments"] or "{}",
                        ),
                    )
                )
            return SimpleNamespace(content=content, tool_calls=built)
        return content

    response = await acall_with_retry(
        lambda: client.chat.completions.create(**kwargs),
        label="desktop_live_chat",
    )
    message = response.choices[0].message
    content = strip_think_blocks(message.content or "")
    if tools is not None:
        return SimpleNamespace(content=content, tool_calls=message.tool_calls)
    return content
