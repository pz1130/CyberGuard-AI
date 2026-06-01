"""Version-gated process-local cache.

Each cache namespace has a Redis integer version key (`cache:ver:<ns>`). On
read we do a cheap GET of that key; if it differs from the locally-stored
version, we reload via the caller's loader and adopt the new version. Writes
INCR the version (and may adopt the new value locally so the writer does not
reload on its next read). If Redis is unreachable, the cache degrades to
loading on every read — correct, just uncached.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Generic, Optional, TypeVar

from app.core.redis_client import get_redis

T = TypeVar("T")


class VersionedCache(Generic[T]):
    def __init__(
        self,
        namespace: str,
        *,
        redis_getter: Callable[[], Awaitable] = get_redis,
    ) -> None:
        self._ver_key = f"cache:ver:{namespace}"
        self._redis_getter = redis_getter
        self._local_version: Optional[str] = None
        self._local_value: Optional[T] = None

    async def get(self, loader: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, reloading via `loader` when the global
        version has advanced (or Redis is unavailable)."""
        try:
            client = await self._redis_getter()
            version = await client.get(self._ver_key)
        except Exception:
            # Redis unavailable: cannot trust local freshness -> reload, do not cache.
            value = await loader()
            self._local_value = value
            self._local_version = None
            return value

        version = version if version is not None else "0"
        if version == self._local_version and self._local_value is not None:
            return self._local_value

        value = await loader()
        self._local_value = value
        self._local_version = version
        return value

    async def bump(self, new_value: Optional[T] = None) -> None:
        """Advance the global version. If `new_value` is given, adopt it locally
        under the new version (so the writer does not reload next read);
        otherwise force the next read to reload."""
        try:
            client = await self._redis_getter()
            new_version = await client.incr(self._ver_key)
            if new_value is not None:
                self._local_value = new_value
                self._local_version = str(new_version)
            else:
                self._local_version = None
        except Exception:
            # Redis down: best-effort local update; peers cannot be notified.
            if new_value is not None:
                self._local_value = new_value
            self._local_version = None
