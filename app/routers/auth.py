"""Authentication router."""
from datetime import timedelta
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.core.auth import create_access_token, verify_token, AuthenticatedUser
from app.schemas.auth import LoginRequest, TokenResponse, RefreshTokenRequest
from app.config import settings

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
async def logout():
    """Logout endpoint (client-side token discard)."""
    return {"message": "Successfully logged out"}


@router.get("/auth/me", tags=["Authentication"])
async def get_current_user_info(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user.to_dict()


@router.post("/auth/refresh", response_model=RefreshResponse, tags=["Authentication"])
async def refresh(body: RefreshTokenRequest):
    """Refresh access token using a valid refresh token."""
    payload = verify_token(body.refresh_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    new_access_token = create_access_token(
        data={"sub": payload["sub"], "username": payload["username"], "role": payload["role"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return RefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
