"""Removing a user deactivates them; it does not delete them.

Deleting was impossible in practice and silently so: conversations.user_id is
NOT NULL with a plain foreign key — no CASCADE, no SET NULL — so removing
anyone who had ever held a conversation raised a constraint violation that
surfaced as a bare 500.

The three alternatives all cost something. Blocking the delete with a clear
message leaves an account that can never be removed. Reassigning their
conversations rewrites who said what. Cascading the delete destroys the
transcripts that Rounds 1 to 3 exist to preserve — the one outcome this
product must not offer.

Deactivating keeps the record intact and takes the account away, which is what
"remove this person's access" actually means here. `get_current_user` already
refuses an inactive user with 403, so it applies to tokens already issued.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers.users import delete_user
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def target():
    """A user with a conversation — the case that used to 500."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"leaver_{suffix}", email=f"leaver_{suffix}@company.local",
                    hashed_password="test-only", role="operator", is_active=True)
        admin = User(username=f"admin_{suffix}", email=f"admin_{suffix}@company.local",
                     hashed_password="test-only", role="admin", is_active=True)
        db.add_all([user, admin])
        await db.flush()
        conv = Conversation(user_id=user.id, title="what they said")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "the thing they said"}])
        await db.commit()
        ids = (user.id, admin.id, admin.username, admin.email, conv.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AuditLog.__table__.delete().where(
            AuditLog.user_id.in_([ids[0], ids[1]])))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[4]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.id == ids[4]))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids[0], ids[1]])))
        await db.commit()


def _actor(target):
    _, admin_id, username, email, _ = target
    return AuthenticatedUser(user_id=admin_id, username=username,
                             email=email, role="admin")


@pytest.mark.asyncio
async def test_removing_a_user_who_owns_a_conversation_no_longer_fails(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()


@pytest.mark.asyncio
async def test_the_user_row_survives_deactivated(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()
        user = await db.get(User, user_id)
        await db.refresh(user)

    assert user is not None, "the row must survive, or the transcripts lose their owner"
    assert user.is_active is False


@pytest.mark.asyncio
async def test_their_transcript_is_untouched(target):
    """The whole reason not to delete."""
    user_id, _, _, _, conv_id = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()
        rows = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conv_id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].content == "the thing they said"


@pytest.mark.asyncio
async def test_the_removal_is_recorded(target):
    """delete_user wrote no audit at all, so nothing said who removed whom."""
    user_id, admin_id, *_ = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.action == "user.deactivate",
            AuditLog.user_id == admin_id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].entry_hash and rows[0].prev_hash


@pytest.mark.asyncio
async def test_deactivating_twice_is_not_an_error(target):
    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()
        await delete_user(user_id, db, _actor(target))
        await db.commit()


@pytest.mark.asyncio
async def test_an_unknown_user_is_still_a_404(target):
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await delete_user(2_000_000_000, db, _actor(target))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_deactivated_user_can_be_restored(target):
    """Deactivation has to be undoable, or it is deletion with extra steps."""
    from app.routers.users import update_user
    from app.schemas.user import UserUpdate

    user_id, *_ = target
    async with AsyncSessionLocal() as db:
        await delete_user(user_id, db, _actor(target))
        await db.commit()
        result = await update_user(user_id, UserUpdate(is_active=True), db,
                                   _actor(target))
    assert result.is_active is True
