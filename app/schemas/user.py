"""Pydantic schemas for user management."""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

from app.schemas.email import InternalEmailStr


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=100)
    email: InternalEmailStr
    full_name: Optional[str] = None
    role: str = "viewer"


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """User update schema.

    ``password`` was missing while ``update_user`` read ``body.password``, so
    every edit — a role change, a deactivation — raised AttributeError and came
    back as a 500, and setting a password from the UI silently kept the old
    one. The same 8-character floor as UserCreate applies, or the update path
    would be a way around the create path's minimum.
    """
    email: Optional[InternalEmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


class UserResponse(BaseModel):
    """User response schema."""
    id: int
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Paginated user list response."""
    total: int
    users: list[UserResponse]

# Aliases
UserRead = UserResponse
