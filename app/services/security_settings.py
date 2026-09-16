"""Security settings service (single-row, version-cached for multi-worker)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.security_settings import SecuritySettings
from app.core.versioned_cache import VersionedCache

_cache: VersionedCache[SecuritySettings] = VersionedCache("security_settings")


async def _load_or_create(db: AsyncSession) -> SecuritySettings:
    result = await db.execute(select(SecuritySettings).where(SecuritySettings.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = SecuritySettings(
            id=1,
            max_login_attempts=5,
            session_timeout_minutes=30,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def _apply_and_refresh(db: AsyncSession, data: dict) -> SecuritySettings:
    cfg = await db.get(SecuritySettings, 1)
    if not cfg:
        return await _load_or_create(db)
    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def get_security_settings(db: AsyncSession) -> SecuritySettings:
    return await _cache.get(lambda: _load_or_create(db))


async def update_security_settings(db: AsyncSession, data: dict) -> SecuritySettings:
    cfg = await _apply_and_refresh(db, data)
    await _cache.bump(cfg)
    return cfg


async def invalidate_cache() -> None:
    await _cache.bump()
