"""User management router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user, require_role
from app.core.auth import AuthenticatedUser
from app.core.rbac import Role
from app.schemas.user import UserCreate, UserRead, UserUpdate, UserListResponse
from app.models.user import User
from app.core.audit import record_action
from app.core.audit_diff import field_diff
from sqlalchemy import select

router = APIRouter()


# One bcrypt policy for the whole codebase — see app.core.auth.
from app.core.auth import get_password_hash as hash_password  # noqa: E402


@router.get("/users", response_model=UserListResponse, dependencies=[Depends(require_role(Role.ADMIN))])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List all users (Admin only)."""
    from sqlalchemy import select, func

    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar()

    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()

    return UserListResponse(total=total, users=[UserRead.model_validate(u) for u in users])


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (Admin only)."""
    from sqlalchemy import select

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    if body.email:
        existing_email = await db.execute(select(User).where(User.email == body.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")

    hashed = hash_password(body.password)
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hashed,
        role=body.role,
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/users/me", response_model=UserRead)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get current authenticated user."""
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)


@router.get("/users/{user_id}", response_model=UserRead, dependencies=[Depends(require_role(Role.ADMIN))])
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID (Admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)


@router.put("/users/{user_id}", response_model=UserRead, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: AuthenticatedUser = Depends(get_current_user),
):
    """Update user (Admin only)."""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # A role change is a privilege change. The HTTP middleware records that
    # someone called this endpoint; without this it would not record what they
    # made of it.
    before = {"email": user.email, "full_name": user.full_name,
              "role": user.role, "is_active": user.is_active,
              "password": user.hashed_password}

    if body.email is not None:
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.hashed_password = hash_password(body.password)

    await db.commit()
    await db.refresh(user)

    changes = field_diff(before, {
        "email": user.email, "full_name": user.full_name,
        "role": user.role, "is_active": user.is_active,
        "password": user.hashed_password,
    })
    if changes:
        await record_action(
            user_id=actor.user_id, action="user.update",
            risk_tier="high" if "role" in changes else "medium",
            human_reviewer=str(actor.user_id),
            input_data={"target_user_id": user_id, "changes": changes},
            output_data={"changed": sorted(changes)},
        )
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete user (Admin only)."""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
