"""Redis client for caching and pub/sub."""
import json
from typing import Optional, Any
import redis.asyncio as redis

from app.config import settings

_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


class RedisCache:
    """Redis cache utility class."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def get(self, key: str) -> Optional[str]:
        r = await self.get_redis()
        return await r.get(key)

    async def set(self, key: str, value: str, expire: int = 3600) -> bool:
        r = await self.get_redis()
        return await r.set(key, value, ex=expire)

    async def delete(self, key: str) -> bool:
        r = await self.get_redis()
        return await r.delete(key) > 0

    async def get_json(self, key: str) -> Optional[Any]:
        data = await self.get(key)
        if data:
            return json.loads(data)
        return None

    async def set_json(self, key: str, value: Any, expire: int = 3600) -> bool:
        return await self.set(key, json.dumps(value, default=str), expire)

    async def publish(self, channel: str, message: Any) -> int:
        r = await self.get_redis()
        return await r.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, channel: str):
        r = await self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        return pubsub


cache = RedisCache()