"""Authentication router."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.dependencies import get_db, get_current_user
from app.core.auth import (
    create_access_token, verify_refresh_token, AuthenticatedUser, revoke_token,
    start_session, touch_session, end_session, end_other_sessions,
)
from app.core import login_guard
from app.schemas.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, PasswordChangeRequest,
)
from app.config import settings

ALGORITHM = settings.ALGORITHM

bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter()


# Re-exported from app.core.auth so there is one bcrypt policy in the codebase
# (72-byte limit handling in particular). Kept as module-level names because
# other modules and tests import them from here.
from app.core.auth import get_password_hash as hash_password  # noqa: E402
from app.core.auth import verify_password  # noqa: E402


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


@router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
async def login(
    request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT access token."""
    from sqlalchemy import select
    from app.models.user import User

    # Checked before the password is even looked at, so a locked account costs
    # an attacker a round trip and nothing else.
    if await login_guard.is_locked(body.username):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Account temporarily locked after repeated failed sign-ins. "
                f"Try again in {login_guard.LOCKOUT_SECONDS // 60} minutes."
            ),
        )

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        # Counted for unknown usernames too: if only real accounts could be
        # locked, the lockout itself would reveal which usernames exist.
        max_attempts = await _max_login_attempts(db)
        count = await login_guard.record_failure(
            body.username, max_attempts=max_attempts)
        if max_attempts and count >= max_attempts:
            from app.core.audit import record_action

            await record_action(
                user_id=getattr(user, "id", None),
                action="auth.account_locked",
                action_category="contain_soft",
                rollback_possible=True,
                input_data={"username": body.username,
                            "client": request.client.host if request.client else None},
                output_data={"attempts": count,
                             "locked_for_seconds": login_guard.LOCKOUT_SECONDS},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    await login_guard.clear(body.username)

    # Name the actor for the audit middleware. This request predates any
    # get_current_user call, so without it the one row that matters most for
    # spotting credential attacks — the login itself — has no user on it.
    # Set only after the credentials check: a failed attempt has no actor,
    # and its 401 plus source IP is the signal there.
    request.state.user_id = user.id
    request.state.username = user.username

    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    await _open_idle_window(db, access_token)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={"id": user.id, "username": user.username, "role": user.role},
    )


@router.post("/auth/logout", tags=["Authentication"])
async def logout(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    """Logout and revoke the current token."""
    if credentials:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti and exp:
                remaining = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
                await revoke_token(jti, remaining)
                await end_session(jti)
        except JWTError:
            pass  # Invalid token already — nothing to revoke
    return {"message": "Successfully logged out"}


async def _max_login_attempts(db: AsyncSession) -> int:
    """The configured attempt limit. Read per request, so lowering it takes
    effect on the next sign-in rather than the next restart."""
    from app.services.security_settings import get_security_settings

    cfg = await get_security_settings(db)
    return int(getattr(cfg, "max_login_attempts", 0) or 0)


async def _idle_minutes(db: AsyncSession) -> int:
    """The configured idle window. Reads the setting that used to be inert."""
    from app.services.security_settings import get_security_settings

    cfg = await get_security_settings(db)
    return int(getattr(cfg, "session_timeout_minutes", 0) or 0)


async def _open_idle_window(db: AsyncSession, access_token: str) -> None:
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:  # pragma: no cover - we just minted it
        return
    jti = payload.get("jti")
    if jti:
        user_id = payload.get("sub")
        await start_session(
            jti, await _idle_minutes(db),
            user_id=int(user_id) if user_id is not None else None)


@router.post("/auth/change-password", tags=["Authentication"])
async def change_password(
    body: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """Change your own password.

    Takes the account from the token and never from the body: a user_id
    parameter here would be an admin endpoint wearing a self-service name.

    The old password is required even though the caller is authenticated. A
    token alone must not be enough to seize the account — otherwise stealing a
    session, which expires, becomes owning the account, which does not.
    """
    from sqlalchemy import select

    from app.core.auth import get_password_hash, verify_password
    from app.core.audit import record_action
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.hashed_password = get_password_hash(body.new_password)
    await db.commit()

    # Changing a password is what someone does when they think it leaked, and
    # that is not answered by rotating the secret while the other session keeps
    # working. The caller's own session is kept so they are not signed out of
    # the tab they are using.
    current_jti = None
    if credentials:
        try:
            current_jti = jwt.decode(
                credentials.credentials, settings.SECRET_KEY,
                algorithms=[ALGORITHM]).get("jti")
        except JWTError:  # pragma: no cover - they just authenticated with it
            current_jti = None
    ended = await end_other_sessions(current_user.user_id, current_jti)

    await record_action(
        user_id=current_user.user_id,
        action="user.password_changed",
        action_category="annotate",
        risk_tier="medium",
        rollback_possible=False,
        input_data={"self_service": True},
        output_data={"other_sessions_ended": ended},
    )

    return {"message": "Password changed", "other_sessions_ended": ended}


@router.post("/auth/heartbeat", tags=["Authentication"])
async def heartbeat(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    _: AuthenticatedUser = Depends(get_current_user),
):
    """Report real user activity, extending the idle window.

    Separate from ordinary requests on purpose: the UI polls several endpoints
    on timers, and a window that any request extended would never close. Only
    the client's interaction listener calls this.
    """
    if not credentials:
        return {"extended": False}
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:  # pragma: no cover - get_current_user already rejected it
        return {"extended": False}

    jti = payload.get("jti")
    minutes = await _idle_minutes(db)
    extended = bool(jti) and await touch_session(jti, minutes)
    return {"extended": extended, "idle_timeout_minutes": minutes}


@router.get("/auth/me", tags=["Authentication"])
async def get_current_user_info(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user.to_dict()


@router.post("/auth/refresh", response_model=RefreshResponse, tags=["Authentication"])
async def refresh(body: RefreshTokenRequest):
    """Refresh access token using a valid refresh token."""
    import asyncio
    payload = await verify_refresh_token(body.refresh_token)

    new_access_token = create_access_token(
        data={"sub": payload["sub"], "username": payload["username"], "role": payload["role"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return RefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
