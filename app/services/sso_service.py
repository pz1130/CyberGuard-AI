"""Azure AD (Entra ID) SSO service.

Splits cleanly into:
  * pure decision logic (`resolve_role`, `decide_provisioning`) — unit-tested, no I/O;
  * DB glue (`get_config`, `provision_or_link_user`);
  * MSAL/OIDC wrappers (`build_auth_url`, `exchange_code`) — `msal` is imported
    lazily so the pure logic remains importable/testable without the dependency.

The client secret is read from `settings.AZURE_CLIENT_SECRET` (env only); it is
never stored in or read from the DB.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.sso import SsoConfig, SsoRoleMapping
from app.models.user import User

logger = logging.getLogger(__name__)

_ROLE_SCOPES = ["openid", "profile", "email"]


class SsoError(Exception):
    """Raised when SSO login cannot complete. ``code`` maps to a login redirect."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


# ---- pure decision logic --------------------------------------------------

def resolve_role(mappings: List[Any], claims: Dict[str, Any], default_role: str) -> str:
    """Resolve an app role from Azure claims via mappings. Highest priority wins."""
    azure_keys = set(claims.get("groups") or []) | set(claims.get("roles") or [])
    matched = [m for m in mappings if m.azure_key in azure_keys]
    if not matched:
        return default_role
    return max(matched, key=lambda m: m.priority).app_role


def decide_provisioning(
    user_by_oid: Optional[Any],
    user_by_email: Optional[Any],
    allow_jit: bool,
) -> Tuple[str, Optional[Any]]:
    """Decide how to map an authenticated Azure user to a local account.

    Returns (action, user) where action is one of:
      "use"            — existing account matched by external_id
      "link_email"     — existing account matched by email; attach external_id
      "create"         — no account; JIT-create
      "reject_inactive"— matched account is disabled
      "reject_no_jit"  — no account and JIT provisioning is off
    """
    found = user_by_oid or user_by_email
    if found is not None:
        if not getattr(found, "is_active", True):
            return ("reject_inactive", found)
        if user_by_oid is None:
            return ("link_email", found)
        return ("use", found)
    if not allow_jit:
        return ("reject_no_jit", None)
    return ("create", None)


# ---- DB glue --------------------------------------------------------------

async def get_config(db: AsyncSession) -> SsoConfig:
    """Fetch the single-row SSO config (creating a disabled default if absent).

    Intentionally not cached — read frequency is low (login/config only) and an
    in-process cache would go stale across workers (see multi-worker-blockers)."""
    cfg = await db.get(SsoConfig, 1)
    if cfg is None:
        cfg = SsoConfig(id=1, enabled=False, default_role="viewer", allow_jit=True)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


def secret_configured() -> bool:
    return bool(settings.AZURE_CLIENT_SECRET)


async def _get_secret(db: AsyncSession, cfg: SsoConfig) -> Optional[str]:
    """Resolve the Azure client secret from a DB EnvVar or the env var."""
    # Prefer the DB EnvVar reference
    if cfg.secret_env_var_id:
        from app.models.envvar import EnvVar
        from app.core.security import CredentialField, decrypt_data
        result = await db.execute(select(EnvVar).where(EnvVar.id == cfg.secret_env_var_id))
        env_var = result.scalar_one_or_none()
        if env_var and env_var.is_active:
            return decrypt_data(env_var.value_encrypted, CredentialField.ENV_VAR_VALUE)
    # Fallback to environment variable
    return settings.AZURE_CLIENT_SECRET or None


async def is_enabled(db: AsyncSession) -> bool:
    """SSO is usable only when toggled on AND fully configured."""
    cfg = await get_config(db)
    secret = await _get_secret(db, cfg)
    return bool(
        cfg.enabled
        and secret
        and cfg.tenant_id
        and cfg.client_id
        and cfg.redirect_uri
    )


async def _get_mappings(db: AsyncSession) -> List[SsoRoleMapping]:
    result = await db.execute(select(SsoRoleMapping))
    return list(result.scalars().all())


async def provision_or_link_user(db: AsyncSession, claims: Dict[str, Any]) -> User:
    """Find/link/create the local user for validated Azure claims and sync role."""
    cfg = await get_config(db)
    oid = claims.get("oid")
    email = (claims.get("email") or "").strip() or None
    if not oid:
        raise SsoError("sso_failed", "Azure token missing oid claim")

    user_by_oid = (
        await db.execute(select(User).where(User.external_id == oid))
    ).scalar_one_or_none()
    user_by_email = None
    if email:
        user_by_email = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    action, user = decide_provisioning(user_by_oid, user_by_email, cfg.allow_jit)
    if action == "reject_inactive":
        raise SsoError("sso_inactive", "User account is disabled")
    if action == "reject_no_jit":
        raise SsoError("sso_no_account", "No matching account and JIT is disabled")

    role = resolve_role(await _get_mappings(db), claims, cfg.default_role)
    from datetime import datetime, timezone

    if action == "create":
        username = (claims.get("preferred_username") or email or oid)[:100]
        # Avoid colliding with an unrelated existing username.
        if (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
            username = f"azuread_{oid}"[:100]
        user = User(
            username=username,
            email=email or f"{oid}@sso.local",
            hashed_password=None,
            role=role,
            is_active=True,
            full_name=claims.get("name"),
            auth_provider="azure_ad",
            external_id=oid,
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
    else:  # "use" or "link_email" — keep identity + role in sync with Azure
        user.auth_provider = "azure_ad"
        user.external_id = oid
        user.role = role
        user.last_login = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    return user


# ---- MSAL / OIDC wrappers (lazy import) -----------------------------------

def _build_msal_app(cfg: SsoConfig, secret: str):
    import msal  # lazy — keeps pure logic importable without the dependency

    authority = f"https://login.microsoftonline.com/{cfg.tenant_id}"
    return msal.ConfidentialClientApplication(
        client_id=cfg.client_id,
        authority=authority,
        client_credential=secret,
    )


def build_auth_url(cfg: SsoConfig, state: str, nonce: str, secret: str) -> str:
    app = _build_msal_app(cfg, secret)
    return app.get_authorization_request_url(
        _ROLE_SCOPES,
        state=state,
        nonce=nonce,
        redirect_uri=cfg.redirect_uri,
    )


def exchange_code(cfg: SsoConfig, code: str, nonce: str, secret: str) -> Dict[str, Any]:
    """Exchange an auth code for tokens and return normalized id_token claims."""
    app = _build_msal_app(cfg, secret)
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=_ROLE_SCOPES,
        redirect_uri=cfg.redirect_uri,
        nonce=nonce,
    )
    if "error" in result or "id_token_claims" not in result:
        logger.warning("SSO token exchange failed: %s", result.get("error_description") or result.get("error"))
        raise SsoError("sso_failed", "Token exchange failed")

    c = result["id_token_claims"]
    return {
        "oid": c.get("oid") or c.get("sub"),
        "email": c.get("email") or c.get("preferred_username") or c.get("upn"),
        "preferred_username": c.get("preferred_username"),
        "name": c.get("name"),
        "groups": c.get("groups") or [],
        "roles": c.get("roles") or [],
    }
