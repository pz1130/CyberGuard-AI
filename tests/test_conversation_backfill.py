"""Migration 041: existing blobs become chained rows, honestly flagged.

The hashes computed here prove only that nothing changed *after* the
migration. The rows are flagged `backfilled` so the trail never claims to
cover the era when the transcript lived in a rewritable blob.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_backfill import rows_for_conversation
from app.services.conversation_chain import verify_conversation_chain


@pytest.mark.asyncio
async def test_a_blob_becomes_a_verifying_chain_of_flagged_rows():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"backfill_{suffix}", email=f"backfill_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(
            user_id=user.id,
            title="imported",
            messages_json=json.dumps([
                {"role": "user", "content": "scan 10.0.0.1",
                 "created_at": "2026-09-01T10:00:00+00:00"},
                {"role": "assistant", "content": "three open ports",
                 "created_at": "2026-09-01T10:00:05+00:00"},
            ]),
        )
        db.add(conv)
        await db.commit()
        conv_id, user_id = conv.id, user.id

        try:
            rows = rows_for_conversation(
                conv_id, conv.messages_json, datetime(2026, 9, 1, 9, 0, 0))
            db.add_all([ConversationMessage(**r) for r in rows])
            await db.commit()

            stored = list((await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conv_id)
                .order_by(ConversationMessage.seq)
            )).scalars().all())

            assert [m.content for m in stored] == ["scan 10.0.0.1", "three open ports"]
            assert [m.role for m in stored] == ["user", "assistant"]
            assert [m.seq for m in stored] == [0, 1]
            assert all(m.backfilled for m in stored), "provenance must be recorded"
            assert verify_conversation_chain(stored) is None
            assert stored[0].created_at.tzinfo is None, "this codebase stores naive UTC"
            assert stored[0].created_at == datetime(2026, 9, 1, 10, 0, 0)
        finally:
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == conv_id))
            await db.execute(Conversation.__table__.delete().where(
                Conversation.user_id == user_id))
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()


def test_a_message_without_a_timestamp_inherits_the_conversations():
    rows = rows_for_conversation(
        5, json.dumps([{"role": "user", "content": "no timestamp"}]),
        datetime(2026, 1, 1, 0, 0, 0))
    assert rows[0]["created_at"] == datetime(2026, 1, 1, 0, 0, 0)


def test_malformed_blobs_yield_nothing_rather_than_failing_the_migration():
    assert rows_for_conversation(5, "not json", datetime(2026, 1, 1)) == []
    assert rows_for_conversation(5, '{"not": "a list"}', datetime(2026, 1, 1)) == []
    assert rows_for_conversation(5, None, datetime(2026, 1, 1)) == []


def test_non_dict_and_non_string_entries_are_coerced_not_dropped_silently():
    rows = rows_for_conversation(5, json.dumps([
        "a bare string",
        {"role": "assistant", "content": {"structured": "answer"}},
    ]), datetime(2026, 1, 1))
    assert len(rows) == 1, "a non-dict entry has no role and is not a message"
    assert rows[0]["content"] == '{"structured": "answer"}'


def test_seq_is_dense_so_the_chain_verifies_even_when_entries_are_skipped():
    rows = rows_for_conversation(5, json.dumps([
        "skipped", {"role": "user", "content": "a"}, "skipped",
        {"role": "user", "content": "b"},
    ]), datetime(2026, 1, 1))
    assert [r["seq"] for r in rows] == [0, 1]
