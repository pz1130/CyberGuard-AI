"""Security settings router."""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.services.security_settings import get_security_settings, update_security_settings

router = APIRouter()


class SecuritySettingsResponse(BaseModel):
    id: int
    encryption_enabled: bool
    rbac_enabled: bool
    audit_logging: bool
    max_login_attempts: int
    session_timeout_minutes: int
    api_key_rotation_days: int

    model_config = ConfigDict(from_attributes=True)


class SecuritySettingsUpdate(BaseModel):
    encryption_enabled: Optional[bool] = None
    rbac_enabled: Optional[bool] = None
    audit_logging: Optional[bool] = None
    max_login_attempts: Optional[int] = None
    session_timeout_minutes: Optional[int] = None
    api_key_rotation_days: Optional[int] = None


@router.get("/security-settings", response_model=SecuritySettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    cfg = await get_security_settings(db)
    return SecuritySettingsResponse.model_validate(cfg)


@router.put("/security-settings", response_model=SecuritySettingsResponse)
async def put_settings(
    body: SecuritySettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    data = body.model_dump(exclude_unset=True)
    cfg = await update_security_settings(db, data)
    return SecuritySettingsResponse.model_validate(cfg)


@router.get("/security/encryption-status")
async def encryption_status(
    _=Depends(require_permission(Permission.SETTINGS_READ)),
):
    """How many stored credentials still use the pre-AEAD format.

    Surfaced so the WebUI can show it: the migration is lazy, so a deployment
    can run indefinitely with malleable ciphertext and no other signal.
    Returns the cached result of the startup scan (see
    app/services/encryption_status.py) — it does not re-scan per request.
    """
    from app.services.encryption_status import get_encryption_status

    return get_encryption_status().to_dict()
