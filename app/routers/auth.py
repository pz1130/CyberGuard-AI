"""Authentication router."""
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.dependencies import get_db, get_current_user
from app.core.auth import create_access_token, verify_refresh_token, AuthenticatedUser, revoke_token
from app.schemas.auth import LoginRequest, TokenResponse, RefreshTokenRequest
from app.config import settings

ALGORITHM = settings.ALGORITHM

bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


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
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT access token."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

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
        except JWTError:
            pass  # Invalid token already — nothing to revoke
    return {"message": "Successfully logged out"}


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
