"""Resilience helpers for outbound LLM provider calls.

Two independent concerns, both keyed by provider:

* ``acall_with_retry`` — retry a provider call with exponential backoff + jitter on
  transient failures (HTTP 429, 5xx, connection/timeout errors), honoring a
  ``Retry-After`` header when the provider sends one. Non-transient errors (4xx
  other than 429, bad requests, auth) propagate immediately — retrying them is
  pointless and would just delay the user-visible failure.
* ``rate_limit`` — a per-provider token bucket throttling requests to a configured
  requests-per-minute ceiling. It is a no-op unless a positive ``rpm`` is given
  (read from the provider's ``metadata_json.rate_limit_rpm``), so existing
  providers are unaffected until someone opts in.

Concept inspired by QwenPaw's retry/rate-limit modules (Apache-2.0); implemented
from scratch against this project's openai-SDK client.
"""
import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    APIStatusError,
)

logger = logging.getLogger(__name__)

# Errors that are worth retrying as-is.
_RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, _RETRYABLE):
        return True
    # Catch-all for providers that surface 429/5xx as a generic status error.
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", 0) or 0
        return code == 429 or code >= 500
    return False


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Extract a Retry-After header (seconds) from an openai SDK error, if present."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if not headers:
        return None
    val = headers.get("retry-after")
    if not val:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


async def acall_with_retry(
    factory: Callable[[], Awaitable],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    label: str = "llm",
):
    """Await ``factory()`` with exponential backoff on transient provider errors.

    ``factory`` must return a *fresh* awaitable on each call (an already-awaited
    coroutine cannot be retried), e.g. ``lambda: client.chat.completions.create(...)``.
    """
    attempt = 0
    while True:
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - we re-raise non-retryable below
            attempt += 1
            if attempt >= max_attempts or not _is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter to avoid thundering herd
            retry_after = _retry_after_seconds(exc)
            if retry_after is not None:
                delay = max(delay, retry_after)
            logger.warning(
                "[%s] transient %s — retry %d/%d in %.1fs",
                label, type(exc).__name__, attempt, max_attempts - 1, delay,
            )
            await asyncio.sleep(delay)


class _TokenBucket:
    """Simple async token bucket: `rate_per_min` tokens, refilled continuously."""

    def __init__(self, rate_per_min: float):
        self.rate_per_min = rate_per_min
        self.capacity = max(1.0, rate_per_min)
        self.tokens = self.capacity
        self.refill_per_sec = rate_per_min / 60.0
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            now = time.monotonic()
            self.tokens = min(
                self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec
            )
            self.updated = now
            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / self.refill_per_sec
                await asyncio.sleep(wait)
                self.tokens = 0.0
                self.updated = time.monotonic()
            else:
                self.tokens -= 1.0


_buckets: dict = {}
_buckets_lock = asyncio.Lock()


async def rate_limit(key, rpm: Optional[float]) -> None:
    """Throttle calls sharing ``key`` to at most ``rpm`` per minute. No-op if rpm falsy."""
    if not rpm or rpm <= 0:
        return
    async with _buckets_lock:
        bucket = _buckets.get(key)
        if bucket is None or bucket.rate_per_min != rpm:
            bucket = _TokenBucket(rpm)
            _buckets[key] = bucket
    await bucket.acquire()
