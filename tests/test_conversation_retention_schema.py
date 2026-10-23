"""The record that makes a purge accountable.

A purged conversation keeps its row, naming the object that holds what was
deleted. Without that, the chain anchors written in Round 1 would point at a
conversation nothing can resolve, and a person's history would silently shrink
rather than show as archived.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.user import User


@pytest.fixture
async def conv():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"ret_{suffix}", email=f"ret_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        row = Conversation(user_id=user.id, title="retained")
        db.add(row)
        await db.commit()
        ids = (row.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


@pytest.mark.asyncio
async def test_an_export_can_be_recorded(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        db.add(ConversationExport(
            conversation_id=conv_id, object_key="conversations/worm/1-2-x.jsonl",
            rows=3, head_seq=2, head_hash="a" * 64,
            retain_until=datetime(2030, 1, 1), exported_at=datetime(2026, 9, 16)))
        await db.commit()

        stored = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == conv_id))).scalar_one()
    assert stored.head_seq == 2
    assert stored.rows == 3
    assert stored.head_hash == "a" * 64


@pytest.mark.asyncio
async def test_a_conversation_can_be_marked_purged(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        row = await db.get(Conversation, conv_id)
        row.purged_at = datetime(2026, 9, 16)
        row.export_key = "conversations/worm/1-2-x.jsonl"
        await db.commit()

        row = await db.get(Conversation, conv_id)
        await db.refresh(row)
    assert row.purged_at is not None
    assert row.export_key.endswith(".jsonl")


@pytest.mark.asyncio
async def test_a_fresh_conversation_is_not_marked_purged(conv):
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        row = await db.get(Conversation, conv_id)
    assert row.purged_at is None
    assert row.export_key is None


@pytest.mark.asyncio
async def test_several_exports_of_one_conversation_coexist(conv):
    """A conversation is re-exported as it grows; the highest head_seq is
    current, and the older rows name objects that still exist in WORM storage
    and cannot be withdrawn."""
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        for head in (2, 9):
            db.add(ConversationExport(
                conversation_id=conv_id, object_key=f"conversations/worm/{head}.jsonl",
                rows=head + 1, head_seq=head, head_hash=str(head) * 64,
                retain_until=None, exported_at=datetime(2026, 9, 16)))
        await db.commit()

        rows = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == conv_id)
            .order_by(ConversationExport.head_seq))).scalars().all()
    assert [r.head_seq for r in rows] == [2, 9]
