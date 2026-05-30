"""Azure AD (Entra ID) SSO router.

Public OIDC flow (status / login / callback) plus admin-only management of the
SSO config and Azure-group → app-role mappings (the "SSO module" under Users).
"""
import logging
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token
from app.core.dependencies import get_db, require_role
from app.core.rbac import Role
from app.core.redis_client import cache
from app.models.sso import SsoConfig, SsoRoleMapping
from app.services import sso_service
from app.services.sso_service import SsoError

router = APIRouter()
logger = logging.getLogger(__name__)

_STATE_TTL = 300  # seconds


# ---------------------------------------------------------------------------
# Public OIDC flow
# ---------------------------------------------------------------------------

@router.get("/auth/sso/status", tags=["SSO"])
async def sso_status(db: AsyncSession = Depends(get_db)):
    """Whether the 'Sign in with Microsoft' button should be shown."""
    return {"enabled": await sso_service.is_enabled(db)}


@router.get("/auth/sso/login", tags=["SSO"])
async def sso_login(db: AsyncSession = Depends(get_db)):
    """Begin the OIDC Authorization Code flow — 302 to Microsoft."""
    if not await sso_service.is_enabled(db):
        return RedirectResponse(url="/?error=sso_unavailable")

    cfg = await sso_service.get_config(db)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    await cache.set_json(f"sso:state:{state}", {"nonce": nonce}, expire=_STATE_TTL)

    auth_url = sso_service.build_auth_url(cfg, state=state, nonce=nonce)
    return RedirectResponse(url=auth_url)


@router.get("/auth/sso/callback", tags=["SSO"])
async def sso_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Microsoft's redirect: validate, provision, mint app JWT."""
    if error or not code or not state:
        return RedirectResponse(url="/?error=sso_failed")

    # Validate + consume single-use state.
    stored = await cache.get_json(f"sso:state:{state}")
    if not stored:
        return RedirectResponse(url="/?error=sso_state")
    await cache.delete(f"sso:state:{state}")

    if not await sso_service.is_enabled(db):
        return RedirectResponse(url="/?error=sso_unavailable")

    cfg = await sso_service.get_config(db)
    try:
        claims = sso_service.exchange_code(cfg, code, nonce=stored["nonce"])
        user = await sso_service.provision_or_link_user(db, claims)
    except SsoError as e:
        return RedirectResponse(url=f"/?error={e.code}")
    except Exception:  # noqa: BLE001 - never leak details to the redirect
        logger.exception("SSO callback failed")
        return RedirectResponse(url="/?error=sso_failed")

    token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return RedirectResponse(url=f"/#sso_token={token}")


# ---------------------------------------------------------------------------
# Admin management ("SSO module")
# ---------------------------------------------------------------------------

class SsoConfigResponse(BaseModel):
    id: int
    enabled: bool
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    default_role: str
    allow_jit: bool
    secret_configured: bool

    model_config = ConfigDict(from_attributes=True)


class SsoConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    redirect_uri: Optional[str] = None
    default_role: Optional[str] = None
    allow_jit: Optional[bool] = None


class RoleMappingCreate(BaseModel):
    azure_key: str
    app_role: str
    priority: int = 10


class RoleMappingResponse(BaseModel):
    id: int
    azure_key: str
    app_role: str
    priority: int

    model_config = ConfigDict(from_attributes=True)


def _config_response(cfg: SsoConfig) -> SsoConfigResponse:
    return SsoConfigResponse(
        id=cfg.id,
        enabled=cfg.enabled,
        tenant_id=cfg.tenant_id,
        client_id=cfg.client_id,
        redirect_uri=cfg.redirect_uri,
        default_role=cfg.default_role,
        allow_jit=cfg.allow_jit,
        secret_configured=sso_service.secret_configured(),
    )


@router.get("/sso/config", response_model=SsoConfigResponse, tags=["SSO"])
async def get_sso_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    cfg = await sso_service.get_config(db)
    return _config_response(cfg)


@router.put("/sso/config", response_model=SsoConfigResponse, tags=["SSO"])
async def update_sso_config(
    body: SsoConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    cfg = await sso_service.get_config(db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)
    return _config_response(cfg)


@router.get("/sso/role-mappings", response_model=list[RoleMappingResponse], tags=["SSO"])
async def list_role_mappings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    result = await db.execute(select(SsoRoleMapping).order_by(SsoRoleMapping.priority.desc()))
    return list(result.scalars().all())


@router.post("/sso/role-mappings", response_model=RoleMappingResponse, tags=["SSO"])
async def create_role_mapping(
    body: RoleMappingCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    existing = (
        await db.execute(select(SsoRoleMapping).where(SsoRoleMapping.azure_key == body.azure_key))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A mapping for this azure_key already exists")
    mapping = SsoRoleMapping(azure_key=body.azure_key, app_role=body.app_role, priority=body.priority)
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


@router.delete("/sso/role-mappings/{mapping_id}", status_code=204, tags=["SSO"])
async def delete_role_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    mapping = await db.get(SsoRoleMapping, mapping_id)
    if mapping:
        await db.delete(mapping)
        await db.commit()
    return None
