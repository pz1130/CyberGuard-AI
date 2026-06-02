"""Optional Langfuse LLM tracing.

Adds per-conversation / per-agent LLM trace visualization (prompts, completions,
model, token usage) on top of the existing OpenTelemetry + token_usage layers.
Mirrors `telemetry.py`: a clean no-op until configured, and any SDK error is
swallowed so tracing can never break an LLM call.

Enable by setting LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST.

Usage (entry points):
    with trace_run(session_id=conversation_id, agent_name="osint", user_id=uid):
        ...                                # LLM calls inside are grouped/tagged

Usage (LLM router, per call):
    record_generation(name="chat", model=m, input=messages, output=text,
                      usage=response.usage)

See: docs/superpowers/specs/2026-06-02-langfuse-llm-tracing-design.md
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Live Langfuse client, or None when unconfigured. Tests inject a fake here.
_client: Optional[Any] = None


@dataclass
class TraceContext:
    session_id: str
    user_id: Optional[int] = None
    agent_name: Optional[str] = None
    tags: Optional[List[str]] = None
    trace: Any = field(default=None)        # live Langfuse trace object, if any


_ctx: ContextVar[Optional[TraceContext]] = ContextVar("langfuse_trace_ctx", default=None)


def setup_langfuse() -> None:
    """Initialise the Langfuse client iff fully configured. Idempotent no-op
    otherwise (missing env or missing package both disable tracing)."""
    global _client
    if _client is not None:
        return
    public = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST")
    if not (public and secret and host):
        logger.debug("Langfuse: not configured — LLM tracing disabled")
        return
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning("Langfuse configured but package missing; run `pip install langfuse`")
        return
    try:
        _client = Langfuse(public_key=public, secret_key=secret, host=host)
        logger.info("Langfuse LLM tracing enabled (host=%s)", host)
    except Exception as e:               # noqa: BLE001 - never fail startup over tracing
        logger.warning("Langfuse init failed: %s", e)


def flush_langfuse() -> None:
    """Flush the async batch (call on shutdown). Safe when unconfigured."""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception as e:               # noqa: BLE001
        logger.debug("Langfuse flush failed: %s", e)


@contextmanager
def trace_run(*, session_id: str, agent_name: Optional[str] = None,
              user_id: Optional[int] = None, tags: Optional[List[str]] = None):
    """Set the trace contextvar (and, when live, open a Langfuse trace carrying
    the session) for the duration of the block. Always resets on exit."""
    trace = None
    if _client is not None:
        try:
            trace = _client.trace(
                name=agent_name or "run", session_id=session_id,
                user_id=str(user_id) if user_id is not None else None, tags=tags)
        except Exception as e:           # noqa: BLE001
            logger.debug("Langfuse trace open failed: %s", e)
    token = _ctx.set(TraceContext(session_id=session_id, user_id=user_id,
                                  agent_name=agent_name, tags=tags, trace=trace))
    try:
        yield
    finally:
        _ctx.reset(token)


def _normalize_usage(usage: Any) -> Optional[Dict[str, int]]:
    """Accept an OpenAI usage object or a dict; emit Langfuse's {input,output,total}."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        pt = usage.get("prompt_tokens", usage.get("input"))
        ct = usage.get("completion_tokens", usage.get("output"))
        tt = usage.get("total_tokens", usage.get("total"))
    else:
        pt = getattr(usage, "prompt_tokens", None)
        ct = getattr(usage, "completion_tokens", None)
        tt = getattr(usage, "total_tokens", None)
    out = {}
    if pt is not None:
        out["input"] = pt
    if ct is not None:
        out["output"] = ct
    if tt is not None:
        out["total"] = tt
    return out or None


def record_generation(*, name: str, model: Optional[str],
                      input: Any, output: Any, usage: Any = None,
                      provider: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> None:
    """Record one LLM generation under the active trace (or as a standalone
    generation if no trace is active). No-op when unconfigured; never raises."""
    if _client is None:
        return
    ctx = _ctx.get()
    target = ctx.trace if (ctx and ctx.trace is not None) else _client
    meta = dict(metadata or {})
    if provider:
        meta["provider"] = provider
    if ctx and ctx.agent_name:
        meta.setdefault("agent", ctx.agent_name)
    try:
        target.generation(name=name, model=model, input=input, output=output,
                          usage=_normalize_usage(usage), metadata=meta or None)
    except Exception as e:               # noqa: BLE001 - tracing must not break the call
        logger.debug("Langfuse record_generation failed: %s", e)
