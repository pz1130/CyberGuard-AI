"""The transcript cannot be rewritten or erased through the API.

PUT /conversations/{id} used to take `messages_json` as a plain string and
write it verbatim: one request replaced the whole transcript, and nothing
recorded that it happened. For a product whose point is evidence of what the
AI said, that is the hole worth closing first.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers.conversations import (
    ConversationResponse,
    ConversationUpdate,
    delete_conversation,
    list_conversations,
    update_conversation,
)
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def seeded():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"immut_{suffix}", email=f"immut_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="evidence")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "is 10.0.0.1 safe to expose"},
            {"role": "assistant", "content": "yes, it is safe"},
        ])
        await db.commit()
        ids = (conv.id, user.id, user.username, user.email, user.role)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


def _user(seeded):
    _, user_id, username, email, role = seeded
    return AuthenticatedUser(user_id=user_id, username=username, email=email, role=role)


def test_the_update_schema_has_no_message_content_field():
    assert "messages_json" not in ConversationUpdate.model_fields, (
        "a message-content field on the update schema is a one-request "
        "transcript rewrite"
    )


def test_the_response_schema_no_longer_ships_the_whole_transcript():
    assert "messages_json" not in ConversationResponse.model_fields


def test_an_unknown_field_on_the_update_is_ignored_not_written():
    body = ConversationUpdate.model_validate(
        {"title": "kept", "messages_json": '[{"role":"assistant","content":"forged"}]'})
    assert body.model_dump(exclude_unset=True) == {"title": "kept"}


@pytest.mark.asyncio
async def test_an_update_cannot_change_a_single_message(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await update_conversation(
            conv_id,
            ConversationUpdate.model_validate({
                "title": "renamed",
                "messages_json": '[{"role":"assistant","content":"no, it is unsafe"}]',
            }),
            db, _user(seeded))
        await db.commit()

        rows = list((await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv_id)
            .order_by(ConversationMessage.seq))).scalars().all())

    assert [r.content for r in rows] == [
        "is 10.0.0.1 safe to expose", "yes, it is safe"]


@pytest.mark.asyncio
async def test_deleting_keeps_the_messages_and_tombstones_the_conversation(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await delete_conversation(conv_id, db, _user(seeded))
        await db.commit()

        conv = (await db.execute(select(Conversation).where(
            Conversation.id == conv_id))).scalar_one_or_none()
        surviving = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conv_id))).scalars().all()

    assert conv is not None, "the conversation row must survive as a tombstone"
    assert conv.deleted_at is not None
    assert conv.deleted_at.tzinfo is None
    assert len(surviving) == 2, "a user must not be able to erase what the AI said"


@pytest.mark.asyncio
async def test_a_tombstoned_conversation_is_hidden_from_the_list(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        await delete_conversation(conv_id, db, _user(seeded))
        await db.commit()
        listed = await list_conversations(db, _user(seeded))
    assert all(c.id != conv_id for c in listed)


@pytest.mark.asyncio
async def test_the_list_reports_a_count_and_a_preview_instead_of_every_message(seeded):
    conv_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(seeded))
    row = next(c for c in listed if c.id == conv_id)
    assert row.message_count == 2
    assert row.last_message_preview == "yes, it is safe"


@pytest.mark.asyncio
async def test_an_empty_conversation_lists_without_a_preview(seeded):
    _, user_id, *_ = seeded
    async with AsyncSessionLocal() as db:
        empty = Conversation(user_id=user_id, title="nothing said yet")
        db.add(empty)
        await db.commit()
        listed = await list_conversations(db, _user(seeded))
    row = next(c for c in listed if c.title == "nothing said yet")
    assert row.message_count == 0
    assert row.last_message_preview is None
