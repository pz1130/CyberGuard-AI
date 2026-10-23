"""Disposing of messages without disposing of the account of them.

The safety property is an ordering: a conversation is purgeable only when an
export object holds every one of its messages. A deployment that cannot
archive therefore cannot delete — which is the state of every deployment here,
since S3 is unconfigured.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_messages import append_messages_locked
from app.services.conversation_purge import purge_eligible


@pytest.fixture
async def world():
    """One old, fully exported conversation and three that must survive."""
    suffix = uuid.uuid4().hex[:8]
    long_ago = utc_now() - timedelta(days=400)
    async with AsyncSessionLocal() as db:
        user = User(username=f"pur_{suffix}", email=f"pur_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()

        made = {}
        for key in ("ready", "unexported", "stale_export", "recent"):
            conv = Conversation(user_id=user.id, title=key)
            db.add(conv)
            await db.flush()
            made[key] = conv.id
        await db.commit()

        for key in list(made):
            await append_messages_locked(db, made[key], [
                {"role": "user", "content": f"{key} one"},
                {"role": "assistant", "content": f"{key} two"},
            ])
        await db.commit()

        # A complete export for "ready"; a stale one for "stale_export".
        db.add(ConversationExport(
            conversation_id=made["ready"], object_key="worm/ready.jsonl",
            rows=2, head_seq=1, head_hash="r" * 64, exported_at=utc_now()))
        db.add(ConversationExport(
            conversation_id=made["stale_export"], object_key="worm/stale.jsonl",
            rows=1, head_seq=0, head_hash="s" * 64, exported_at=utc_now()))
        await db.commit()

        # Age everything except "recent".
        for key in ("ready", "unexported", "stale_export"):
            conv = await db.get(Conversation, made[key])
            conv.updated_at = long_ago
        await db.commit()

        made["user"] = user.id
    yield made
    async with AsyncSessionLocal() as db:
        ids = [v for k, v in made.items() if k != "user"]
        await db.execute(AuditLog.__table__.delete().where(
            AuditLog.user_id == made["user"]))
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_(ids)))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_(ids)))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == made["user"]))
        await db.execute(User.__table__.delete().where(User.id == made["user"]))
        await db.commit()


async def _purge(confirm):
    async with AsyncSessionLocal() as db:
        summary = await purge_eligible(db, older_than_days=365, confirm=confirm)
        await db.commit()
    return summary


def _ids(summary):
    return {c["conversation_id"] for c in summary["conversations"]}


# --- eligibility ---

@pytest.mark.asyncio
async def test_an_old_fully_exported_conversation_is_eligible(world):
    assert world["ready"] in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_an_unexported_conversation_is_never_eligible(world):
    """The safety property: nothing is deleted that was not first archived."""
    assert world["unexported"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_a_partially_exported_conversation_is_not_eligible(world):
    """Exported at seq 0 but now at seq 1 — purging would lose a message that
    exists in no object."""
    assert world["stale_export"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_a_recently_updated_conversation_is_not_eligible(world):
    assert world["recent"] not in _ids(await _purge(confirm=False))


@pytest.mark.asyncio
async def test_an_already_purged_conversation_is_not_offered_again(world):
    await _purge(confirm=True)
    assert _ids(await _purge(confirm=False)) == set()


# --- the dry run ---

@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing(world):
    summary = await _purge(confirm=False)
    assert summary["dry_run"] is True
    assert summary["messages_deleted"] == 0

    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["ready"]))).scalars().all()
        conv = await db.get(Conversation, world["ready"])
    assert len(remaining) == 2
    assert conv.purged_at is None


# --- the purge ---

@pytest.mark.asyncio
async def test_confirming_deletes_every_message_of_the_conversation(world):
    summary = await _purge(confirm=True)
    assert summary["dry_run"] is False
    assert summary["messages_deleted"] == 2

    async with AsyncSessionLocal() as db:
        remaining = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["ready"]))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_the_conversation_survives_as_an_archived_record(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, world["ready"])
        await db.refresh(conv)
    assert conv is not None, "the row must survive so the chain anchors resolve"
    assert conv.purged_at is not None
    assert conv.export_key == "worm/ready.jsonl"
    assert conv.title == "ready", "the person should still see what it was"


@pytest.mark.asyncio
async def test_untouched_conversations_keep_their_messages(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        for key in ("unexported", "stale_export", "recent"):
            rows = (await db.execute(select(ConversationMessage).where(
                ConversationMessage.conversation_id == world[key]))).scalars().all()
            assert len(rows) == 2, f"{key} lost messages it should have kept"


@pytest.mark.asyncio
async def test_the_deletion_is_recorded_in_the_global_audit_chain(world):
    await _purge(confirm=True)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["user"],
            AuditLog.action == "conversation.purged"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action_category == "remediate"
    assert rows[0].entry_hash and rows[0].prev_hash


# --- the operability constraint ---

@pytest.mark.asyncio
async def test_nothing_is_eligible_when_nothing_could_be_exported(world):
    """With S3 unconfigured no export row is ever written, so this is what a
    real deployment here sees: purge finds nothing, however old the data."""
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_(
                [world["ready"], world["stale_export"]])))
        await db.commit()

    assert _ids(await _purge(confirm=False)) == set()
