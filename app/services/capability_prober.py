"""Probe a provider's model for optional capabilities (function-calling, vision).

Each probe sends one minimal chat request through the provider's own client and
classifies the outcome:

* HTTP 200            -> capability supported (True)
* HTTP 400 / 422      -> provider rejected the feature -> not supported (False)
* anything else       -> unknown (None); not cached as False, so a transient 429/
                         5xx or network blip doesn't get recorded as "unsupported"

Results are written back inline onto the provider's stored model list
(``models[i]["capabilities"]``) so they travel with the model and show up in the
provider API responses. Probing is on-demand only — it is never run automatically,
to avoid spending the user's API quota behind their back.

Capability concept inspired by QwenPaw's prober (Apache-2.0); implemented fresh.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from openai import APIStatusError

logger = logging.getLogger(__name__)

# Smallest valid request payloads. max_tokens=1 keeps the spend negligible.
_PROBE_MESSAGES = [{"role": "user", "content": "hi"}]
_PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "ping",
        "description": "probe tool",
        "parameters": {"type": "object", "properties": {}},
    },
}]
# 1x1 transparent PNG (public-domain pixel) as a data URL for the vision probe.
_PIXEL_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _classify(exc: Optional[Exception]) -> Optional[bool]:
    """None exc = success (True). 400/422 = unsupported (False). Else unknown (None)."""
    if exc is None:
        return True
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", 0) or 0
        if code in (400, 422):
            return False
    return None


async def _run_probe(client, model: str, *, extra: dict) -> Optional[bool]:
    kwargs: dict = {"model": model, "messages": _PROBE_MESSAGES, "max_tokens": 1}
    kwargs.update(extra)  # extra may override messages (vision probe)
    try:
        await client.chat.completions.create(**kwargs)
        return _classify(None)
    except Exception as exc:  # noqa: BLE001 - classified, not swallowed blindly
        result = _classify(exc)
        if result is None:
            logger.info("[capability_prober] %s indeterminate: %s", model, type(exc).__name__)
        return result


async def probe_model(client, model: str) -> dict[str, Any]:
    """Probe a single model for tools + vision support. Returns a capabilities dict."""
    tools = await _run_probe(client, model, extra={"tools": _PROBE_TOOL, "tool_choice": "auto"})
    vision = await _run_probe(client, model, extra={"messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": _PIXEL_DATA_URL}},
        ],
    }]})
    return {
        "tools": tools,
        "vision": vision,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
