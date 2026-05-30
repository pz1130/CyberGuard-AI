"""Security settings service (single-row, cached)."""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.security_settings import SecuritySettings

_cache: Optional[SecuritySettings] = None


async def get_security_settings(db: AsyncSession) -> SecuritySettings:
    global _cache
    if _cache is not None:
        return _cache

    result = await db.execute(select(SecuritySettings).where(SecuritySettings.id == 1))
    cfg = result.scalar_one_or_none()

    if cfg is None:
        cfg = SecuritySettings(
            id=1,
            encryption_enabled=True,
            rbac_enabled=True,
            audit_logging=True,
            max_login_attempts=5,
            session_timeout_minutes=30,
            api_key_rotation_days=90,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

    _cache = cfg
    return cfg


async def update_security_settings(db: AsyncSession, data: dict) -> SecuritySettings:
    global _cache
    cfg = await db.get(SecuritySettings, 1)
    if not cfg:
        return await get_security_settings(db)

    for key, value in data.items():
        if hasattr(cfg, key) and value is not None:
            setattr(cfg, key, value)

    await db.commit()
    await db.refresh(cfg)
    _cache = cfg
    return cfg


def invalidate_cache() -> None:
    global _cache
    _cache = None
