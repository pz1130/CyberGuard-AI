"""Pydantic schemas for authentication."""
from pydantic import BaseModel, Field

from app.schemas.email import InternalEmailStr
from typing import Optional


class LoginRequest(BaseModel):
    """Login request schema."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token response schema."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    """JWT token payload schema."""
    user_id: int
    username: str
    email: str
    role: str
    exp: int
    iat: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str


class RegisterRequest(BaseModel):
    """User registration request schema."""
    username: str = Field(..., min_length=3, max_length=100)
    email: InternalEmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: str = "viewer"


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""
    old_password: str
    new_password: str = Field(..., min_length=8)


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: InternalEmailStr


class SetPasswordRequest(BaseModel):
    """Set new password from reset token."""
    token: str
    new_password: str = Field(..., min_length=8)