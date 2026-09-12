"""Cross-worker maintenance coordination."""
from app.core.redis_client import get_redis


DATABASE_RESTORE_KEY = "maintenance:database_restore"


async def database_restore_in_progress() -> bool:
    client = await get_redis()
    try:
        return bool(await client.get(DATABASE_RESTORE_KEY))
    finally:
        await client.aclose()


async def acquire_database_restore(token: str, ttl_seconds: int = 900) -> bool:
    client = await get_redis()
    try:
        return bool(await client.set(DATABASE_RESTORE_KEY, token, ex=ttl_seconds, nx=True))
    finally:
        await client.aclose()


async def release_database_restore(token: str) -> None:
    client = await get_redis()
    try:
        await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            DATABASE_RESTORE_KEY,
            token,
        )
    finally:
        await client.aclose()
