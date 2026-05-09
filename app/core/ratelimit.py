"""Redis-based rate limiting for API endpoints.

Implements a sliding window counter per user using Redis.
Configurable via environment variables:

    RATELIMIT_REQUESTS_PER_MINUTE  — max chat requests per minute (default: 30)
    RATELIMIT_REQUESTS_PER_HOUR    — max chat requests per hour (default: 500)
    RATELIMIT_BURST                — max concurrent in-flight requests per user (default: 5)
"""
import time
import logging
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

# Redis connection pool (lazy singleton)
_redis_pool: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            settings.REDIS_URL or "redis://localhost:6379/0",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None


def _parse_int(val: Optional[str], default: int) -> int:
    if val is None:
        return default
    try:
        return max(1, int(val))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Sliding window rate limit check
# ---------------------------------------------------------------------------

async def check_rate_limit(
    user_id: int,
    window_seconds: int = 60,
    max_requests: int = 30,
    key_prefix: str = "ratelimit",
) -> tuple[bool, int, int]:
    """
    Check and increment rate limit for a user using sliding window counter.

    Returns (allowed, remaining, reset_at_unix).
    reset_at_unix = current time + window_seconds.
    """
    r = await get_redis()
    now = time.time()
    window_start = now - window_seconds

    key = f"{key_prefix}:{user_id}"

    # Use a Redis sorted set:
    # score = timestamp, member = unique event id
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
    pipe.zcard(key)                               # Count current entries
    pipe.zadd(key, {f"{now}::{time.time_ns()}": now})  # Add this request
    pipe.expire(key, window_seconds + 1)          # Auto-cleanup

    results = await pipe.execute()
    current_count = results[1]  # zcard before zadd

    remaining = max(0, max_requests - current_count - 1)
    reset_at = int(now + window_seconds)

    if current_count >= max_requests:
        return False, remaining, reset_at

    return True, remaining, reset_at


# ---------------------------------------------------------------------------
# Per-user concurrency limit (burst protection)
# ---------------------------------------------------------------------------

async def check_concurrency_limit(
    user_id: int,
    max_concurrent: int = 5,
    key_prefix: str = "concurrency",
) -> tuple[bool, int]:
    """
    Check in-flight request count using a Redis counter.

    Returns (allowed, current_inflight).
    Increments on entry, decrements via release_concurrency().
    """
    r = await get_redis()
    key = f"{key_prefix}:{user_id}"

    # Increment atomically; check if we exceed the limit
    count = await r.incr(key)
    await r.expire(key, 300)  # 5 min TTL on counter

    if count > max_concurrent:
        # Already over — decrement to keep count accurate
        await r.decr(key)
        return False, count - 1

    return True, count


async def release_concurrency(user_id: int, key_prefix: str = "concurrency"):
    """Decrement in-flight counter when a request completes."""
    r = await get_redis()
    key = f"{key_prefix}:{user_id}"
    val = await r.decr(key)
    if val < 0:
        # Shouldn't go negative — reset
        await r.set(key, 0)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

class RateLimitExceeded(HTTPException):
    """Raised when a user exceeds their rate limit."""

    def __init__(self, retry_after: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


class ConcurrencyLimitExceeded(HTTPException):
    """Raised when a user has too many in-flight requests."""

    def __init__(self, current: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many in-flight requests ({current}). Please wait for pending responses.",
            headers={"Retry-After": "10"},
        )


async def rate_limit_dependency(
    user_id: int,
    requests_per_minute: int = 30,
    requests_per_hour: int = 500,
    burst_limit: int = 5,
):
    """
    FastAPI dependency that enforces per-user rate limits using Redis sliding window.

    Uses a Redis sorted set per user for O(1) sliding window counting.
    Raises HTTPException 429 on violation. Releases concurrency slot on yield.

    Usage — pass user_id from require_permission (or any auth dependency):
        @router.post("/chat", ...)
        async def chat(
            body: ChatRequest,
            current_user: AuthenticatedUser = Depends(require_permission(...)),
            _=Depends(rate_limit_dependency(user_id=current_user.user_id)),
        ):
            ...
    """
    import os as _os

    rpm = requests_per_minute or _parse_int(_os.getenv("RATELIMIT_REQUESTS_PER_MINUTE"), 30)
    rph = requests_per_hour or _parse_int(_os.getenv("RATELIMIT_REQUESTS_PER_HOUR"), 500)
    burst = burst_limit or _parse_int(_os.getenv("RATELIMIT_BURST"), 5)

    from fastapi import HTTPException, status

    # Per-minute sliding window
    allowed, remaining, reset_at = await check_rate_limit(
        user_id=user_id,
        window_seconds=60,
        max_requests=rpm,
        key_prefix="ratelimit:minute",
    )
    if not allowed:
        retry_after = max(1, reset_at - int(time.time()))
        raise RateLimitExceeded(retry_after=retry_after)

    # Per-hour sliding window
    allowed, remaining, reset_at = await check_rate_limit(
        user_id=user_id,
        window_seconds=3600,
        max_requests=rph,
        key_prefix="ratelimit:hour",
    )
    if not allowed:
        retry_after = max(1, reset_at - int(time.time()))
        raise RateLimitExceeded(retry_after=retry_after)

    # Acquire concurrency slot
    allowed, current = await check_concurrency_limit(
        user_id=user_id,
        max_concurrent=burst,
        key_prefix="concurrency",
    )
    if not allowed:
        raise ConcurrencyLimitExceeded(current=current)

    # Yield — runs on response exit to release concurrency slot
    try:
        yield
    finally:
        await release_concurrency(user_id)
