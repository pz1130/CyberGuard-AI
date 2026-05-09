"""
OpenTelemetry instrumentation for CyberGuard.

Spans cover:
  - HTTP requests (via FastAPI instrumentation)
  - LLM chat completions (OpenAI calls wrapped with spans)
  - DB queries (via SQLAlchemy instrumentation)
  - Celery tasks (via celery instrumentation)

Exporter configured via env:
    OTEL_EXPORTER_OTLP_ENDPOINT  — collector endpoint (e.g. http://localhost:4317)
    OTEL_SERVICE_NAME           — service identifier (default: cyberguard)
    OTEL_TRACES_SAMPLER          — always_on | traceidratio | parentbased_always_off

No-op when env vars are absent (safe for local dev without an OTel backend).
"""
from __future__ import annotations

import logging
from typing import Collection, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tracing bootstrap — call once at startup
# ---------------------------------------------------------------------------

_tracer_provider: Optional[object] = None


def setup_telemetry() -> None:
    """
    Initialise OpenTelemetry tracing and attach to FastAPI/Celery/SQLAlchemy.

    Idempotent — safe to call multiple times.
    """
    global _tracer_provider

    endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None) or _env("OTEL_EXPORTER_OTLP_ENDPOINT")
    service_name = _env("OTEL_SERVICE_NAME", "cyberguard")

    if not endpoint:
        logger.debug("OpenTelemetry: no OTEL_EXPORTER_OTLP_ENDPOINT set — tracing disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.trace.sampling import _getSampler
    except ImportError as e:
        logger.warning(f"OpenTelemetry dependencies missing: {e}. Install: pip install opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy")
        return

    sampler = _get_sampler()

    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource, sampler=sampler)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    # Attach FastAPI instrumentation
    try:
        _instrument_fastapi()
    except Exception as e:
        logger.warning(f"FastAPI instrumentation failed: {e}")

    # Attach SQLAlchemy instrumentation
    try:
        _instrument_sqlalchemy()
    except Exception as e:
        logger.warning(f"SQLAlchemy instrumentation failed: {e}")

    # Attach Celery instrumentation
    try:
        _instrument_celery()
    except Exception as e:
        logger.warning(f"Celery instrumentation failed: {e}")

    logger.info(f"OpenTelemetry tracing enabled — endpoint={endpoint}, service={service_name}")


def _env(key: str, default: str = "") -> str:
    import os
    return os.environ.get(key, default) or default


def _get_sampler():
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ParentBased, AlwaysOnSampler, AlwaysOffSampler
    sampler_arg = _env("OTEL_TRACES_SAMPLER", "parentbased_always_on").lower()
    if sampler_arg == "always_off":
        return ParentBased(AlwaysOffSampler())
    if sampler_arg == "traceidratio":
        ratio = float(_env("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        return TraceIdRatioBased(ratio)
    return ParentBased(AlwaysOnSampler())  # default: parent-based always on


def _instrument_fastapi():
    """Attach OpenTelemetry spans to incoming HTTP requests."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from app.main import app

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/docs,/openapi.json")

    # Add trace context propagation to the audit middleware
    # (already covered by FastAPI instrumentation)


def _instrument_sqlalchemy():
    """Attach OpenTelemetry spans to all SQLAlchemy DB operations."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from app.core.database import engine

    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        enable_commenter=True,
    )


def _instrument_celery():
    """Attach OpenTelemetry spans to Celery task dispatch and execution."""
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
    except ImportError:
        pass  # celery may not be installed in all environments


# ---------------------------------------------------------------------------
# Span helpers — use these in hot paths instead of raw tracer.start_span
# ---------------------------------------------------------------------------

def get_tracer(name: str = "cyberguard"):
    """Return the global tracer for the given module name."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpSpan:
    """No-op span — used when OTel is not configured."""
    def set_attribute(self, key, value): return self
    def set_attributes(self, attrs): return self
    def add_event(self, name, attrs=None): return self
    def record_exception(self, exc): pass
    def set_status(self, status): return self
    def end(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    """No-op tracer — used when OTel is not configured."""
    def start_span(self, name, **kwargs): return _NoOpSpan()
    def start_as_current_span(self, name, **kwargs): return _NoOpSpan()


# ---------------------------------------------------------------------------
# LLM span helper — wraps OpenAI API calls with structured attributes
# ---------------------------------------------------------------------------

def trace_llm_call(
    tracer,
    model: str,
    provider: str,
    operation: str,  # "chat" | "embed"
    extra_attributes: Optional[dict] = None,
):
    """
    Decorator/context manager to trace an LLM API call.

    Usage (context manager):
        tracer = get_tracer()
        with trace_llm_call(tracer, model="gpt-4o", provider="openai", operation="chat"):
            result = await client.chat.completions.create(...)

    Usage (decorator):
        @trace_llm_call(tracer, model="gpt-4o", ...)
        async def my_llm_call(...):
            ...
    """
    span_name = f"llm.{operation}"
    attributes = {
        "llm.model": model,
        "llm.provider": provider,
        "llm.operation": operation,
    }
    if extra_attributes:
        attributes.update(extra_attributes)

    return tracer.start_as_current_span(span_name, kind=None, attributes=attributes)


# ---------------------------------------------------------------------------
# Celery task span helper
# ---------------------------------------------------------------------------

def trace_celery_task(tracer, task_name: str, task_kwargs: Optional[dict] = None):
    """
    Wrap a Celery task's body with a span.

    Usage in tasks.py:
        from app.core.telemetry import get_tracer, trace_celery_task

        tracer = get_tracer()
        with trace_celery_task(tracer, "run_master_agent_task", {"execution_id": execution_id}):
            # ... task body ...
            pass
    """
    attrs = {
        "celery.task": task_name,
        "celery.queue": _env("CELERY_QUEUE_NAME", "cyberguard"),
    }
    if task_kwargs:
        # Scrub sensitive fields
        sensitive = {"api_key", "password", "token", "secret", "hashed_password"}
        safe = {k: ("***" if k.lower() in sensitive else v) for k, v in task_kwargs.items()}
        attrs["celery.task_kwargs"] = str(safe)

    return tracer.start_as_current_span(f"celery.{task_name}", attributes=attrs)
