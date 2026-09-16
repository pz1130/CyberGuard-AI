"""Editing a user — every PUT /users/{id} raised 500.

`update_user` reads `body.password`, but `UserUpdate` never declared the field,
so pydantic raised AttributeError on the attribute access and the endpoint
returned "Internal server error" for *any* edit: a role change, a deactivation,
an email correction. Setting a password through the UI appeared to succeed and
silently kept the old one.

The form has always shown a NEW PASSWORD box with "leave blank to keep
current", so the intent was there; the field was simply missing from the
schema.
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.auth import AuthenticatedUser, verify_password
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.routers.users import update_user
from app.schemas.user import UserUpdate


def test_the_update_schema_accepts_a_password():
    assert "password" in UserUpdate.model_fields
    assert UserUpdate(password="Str0ng-Pass-123").password == "Str0ng-Pass-123"


def test_omitting_the_password_leaves_it_unset():
    """"Leave blank to keep current" has to mean exactly that."""
    assert UserUpdate(role="analyst").password is None


def test_a_short_password_is_refused_on_update_as_on_create():
    """Otherwise the update path is a way around the create path's floor."""
    with pytest.raises(ValidationError):
        UserUpdate(password="short")


@pytest.fixture
async def target():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        from app.core.auth import get_password_hash

        user = User(username=f"upd_{suffix}", email=f"upd_{suffix}@company.local",
                    hashed_password=get_password_hash("Original-Pass-1"),
                    role="viewer", is_active=True)
        db.add(user)
        actor = User(username=f"act_{suffix}", email=f"act_{suffix}@company.local",
                     hashed_password="test-only", role="admin", is_active=True)
        db.add(actor)
        await db.commit()
        ids = (user.id, actor.id, actor.username, actor.email)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(User.__table__.delete().where(User.id.in_([ids[0], ids[1]])))
        await db.commit()


def _actor(target):
    _, actor_id, username, email = target
    return AuthenticatedUser(user_id=actor_id, username=username,
                             email=email, role="admin")


@pytest.mark.asyncio
async def test_changing_only_the_role_no_longer_raises(target):
    """The bug was not about passwords: every edit hit the same attribute."""
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        result = await update_user(user_id, UserUpdate(role="analyst"), db, _actor(target))
    assert result.role == "analyst"


@pytest.mark.asyncio
async def test_a_new_password_actually_replaces_the_old_one(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await update_user(user_id, UserUpdate(password="Replaced-Pass-2"), db, _actor(target))
        user = await db.get(User, user_id)
        await db.refresh(user)

    assert verify_password("Replaced-Pass-2", user.hashed_password)
    assert not verify_password("Original-Pass-1", user.hashed_password), (
        "the old password still works, so the change did not take effect"
    )


@pytest.mark.asyncio
async def test_an_edit_that_omits_the_password_keeps_it(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await update_user(user_id, UserUpdate(role="operator"), db, _actor(target))
        user = await db.get(User, user_id)
        await db.refresh(user)

    assert verify_password("Original-Pass-1", user.hashed_password)


@pytest.mark.asyncio
async def test_the_stored_password_is_hashed_not_the_plain_text(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await update_user(user_id, UserUpdate(password="Replaced-Pass-2"), db, _actor(target))
        user = await db.get(User, user_id)
        await db.refresh(user)
    assert "Replaced-Pass-2" not in user.hashed_password
