"""Security settings router."""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.dependencies import get_db, get_current_user, require_permission
from app.core.rbac import Permission
from app.services.security_settings import get_security_settings, update_security_settings

router = APIRouter()


class SecuritySettingsResponse(BaseModel):
    id: int
    # Only what is enforced. See tests/test_security_settings_shape.py for why
    # encryption / RBAC / audit are not switches.
    max_login_attempts: int
    session_timeout_minutes: int

    model_config = ConfigDict(from_attributes=True)


class SecuritySettingsUpdate(BaseModel):
    max_login_attempts: Optional[int] = Field(default=None, ge=3, le=20)
    session_timeout_minutes: Optional[int] = Field(default=None, ge=5, le=480)


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
    actor: AuthenticatedUser = Depends(get_current_user),
    _=Depends(require_permission(Permission.SETTINGS_WRITE)),
):
    from app.core.audit import record_action
    from app.core.audit_diff import field_diff

    data = body.model_dump(exclude_unset=True)
    current = await get_security_settings(db)
    before = {k: getattr(current, k, None) for k in data}

    cfg = await update_security_settings(db, data)

    # Turning off audit_logging, or widening the session window, are exactly the
    # changes someone would make to cover their tracks — so they are recorded
    # before anything else about the trail is trusted.
    changes = field_diff(before, {k: getattr(cfg, k, None) for k in data})
    if changes:
        await record_action(
            user_id=actor.user_id, action="security_settings.update",
            risk_tier="high",
            human_reviewer=str(actor.user_id),
            input_data={"changes": changes},
            output_data={"changed": sorted(changes)},
        )
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
