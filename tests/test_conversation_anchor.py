"""Anchoring: what makes a deleted conversation detectable.

The per-conversation chain proves no message inside a conversation was
altered, reordered or removed. It cannot prove the conversation existed —
delete every row and nothing is left to be inconsistent. Writing each chain
head into the global audit chain is what closes that.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, get_sync_session
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_anchor import ANCHOR_ACTION, anchor_pending
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def seeded():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"anchor_{suffix}", email=f"anchor_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="anchored")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
        await db.commit()
        ids = (conv.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AuditLog.__table__.delete().where(AuditLog.user_id == ids[1]))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


def _run_anchor():
    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        summary = anchor_pending(session)
        session.commit()
    return summary


def _count_anchors_sync(user_id: int) -> int:
    SessionLocal = get_sync_session()
    with SessionLocal() as session:
        return len(session.execute(select(AuditLog).where(
            AuditLog.user_id == user_id,
            AuditLog.action == ANCHOR_ACTION)).scalars().all())


@pytest.mark.asyncio
async def test_anchoring_records_the_head_and_advances_the_marker(seeded):
    conv_id, user_id = seeded
    assert _run_anchor()["anchored"] >= 1

    async with AsyncSessionLocal() as db:
        conv = (await db.execute(select(Conversation).where(
            Conversation.id == conv_id))).scalar_one()
        head = (await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv_id)
            .order_by(ConversationMessage.seq.desc()).limit(1))).scalar_one()
        anchors = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == user_id, AuditLog.action == ANCHOR_ACTION))).scalars().all()

    assert conv.last_anchored_seq == head.seq == 1
    assert len(anchors) == 1
    assert anchors[0].entry_hash and anchors[0].prev_hash


@pytest.mark.asyncio
async def test_a_second_run_with_nothing_new_writes_nothing(seeded):
    _, user_id = seeded
    _run_anchor()
    before = _count_anchors_sync(user_id)
    assert _run_anchor()["anchored"] == 0
    assert _count_anchors_sync(user_id) == before


@pytest.mark.asyncio
async def test_new_messages_after_an_anchor_produce_another_one(seeded):
    conv_id, user_id = seeded
    _run_anchor()
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, conv_id, [{"role": "user", "content": "c"}])
        await db.commit()
    assert _run_anchor()["anchored"] >= 1
    assert _count_anchors_sync(user_id) == 2


@pytest.mark.asyncio
async def test_a_conversation_with_no_messages_is_not_anchored(seeded):
    """-1 as the starting marker must not read as "seq 0 is pending"."""
    _, user_id = seeded
    async with AsyncSessionLocal() as db:
        empty = Conversation(user_id=user_id, title="silent")
        db.add(empty)
        await db.commit()
        empty_id = empty.id
    _run_anchor()
    async with AsyncSessionLocal() as db:
        conv = (await db.execute(select(Conversation).where(
            Conversation.id == empty_id))).scalar_one()
    assert conv.last_anchored_seq == -1


@pytest.mark.asyncio
async def test_the_anchor_links_into_the_global_chain(seeded):
    """An anchor is an ordinary audit row: if it broke the chain it would be
    worse than not anchoring at all.

    Asserted on the anchor row and its immediate predecessor rather than via
    `verify_chain()` over the whole table: the shared test database already
    carries synthetic rows written by test_audit_chain.py, so the global
    verify is False before this test does anything. The local property is the
    one anchoring is responsible for anyway.
    """
    from app.core.audit import _row_chain_payload, stamp_chain_hashes

    _run_anchor()

    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(
            select(AuditLog).order_by(AuditLog.id.desc()).limit(2))).scalars().all())

    anchor, predecessor = rows[0], rows[1]
    assert anchor.action == ANCHOR_ACTION
    assert anchor.prev_hash == predecessor.entry_hash, (
        "the anchor did not link to the row before it")
    recomputed = stamp_chain_hashes(_row_chain_payload(anchor), anchor.prev_hash)
    assert recomputed["entry_hash"] == anchor.entry_hash, (
        "the anchor's own hash does not recompute from its stored fields")


def test_the_sync_audit_writer_links_to_the_same_chain():
    """record_action_sync exists because Celery is sync; it must produce rows
    indistinguishable from record_action's."""
    from app.core.audit import record_action_sync

    payload = record_action_sync(
        user_id=None, action="test.sync_chain_writer",
        action_category="annotate", input_data={"a": 1}, output_data={"b": 2})
    assert len(payload["entry_hash"]) == 64
    assert len(payload["prev_hash"]) == 64
    assert payload["chain_version"] == 2
