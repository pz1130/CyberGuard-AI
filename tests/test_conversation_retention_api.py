"""What retention looks like from outside.

An archived conversation still appears with its title: "your conversation is
empty" would be a lie, and a history that silently shrinks is worse than one
that says what happened to it.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers.conversations import (
    AppendMessageRequest, append_message, list_conversations,
)


@pytest.fixture
async def archived():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"arch_{suffix}", email=f"arch_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="Archived work",
                            purged_at=utc_now(), export_key="worm/a.jsonl")
        live = Conversation(user_id=user.id, title="Still here")
        db.add_all([conv, live])
        await db.commit()
        ids = (conv.id, live.id, user.id, user.username, user.email)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_([ids[0], ids[1]])))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[2]))
        await db.execute(User.__table__.delete().where(User.id == ids[2]))
        await db.commit()


def _user(archived):
    _, _, user_id, username, email = archived
    return AuthenticatedUser(user_id=user_id, username=username,
                             email=email, role="admin")


@pytest.mark.asyncio
async def test_an_archived_conversation_is_still_listed(archived):
    conv_id, *_ = archived
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(archived))
    row = next(c for c in listed if c.id == conv_id)
    assert row.archived is True
    assert row.title == "Archived work"
    assert row.message_count == 0


@pytest.mark.asyncio
async def test_a_live_conversation_is_not_marked_archived(archived):
    _, live_id, *_ = archived
    async with AsyncSessionLocal() as db:
        listed = await list_conversations(db, _user(archived))
    assert next(c for c in listed if c.id == live_id).archived is False


@pytest.mark.asyncio
async def test_appending_to_an_archived_conversation_is_refused(archived):
    """Resuming it would start a second chain at seq 0, colliding with the one
    already exported."""
    from fastapi import HTTPException

    conv_id, *_ = archived
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await append_message(
                conv_id, AppendMessageRequest(role="user", content="more"),
                db, _user(archived))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_nothing_is_written_when_the_append_is_refused(archived):
    """The exception must land before the commit, or the 409 would be a lie."""
    from fastapi import HTTPException
    from sqlalchemy import select

    conv_id, *_ = archived
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException):
            await append_message(
                conv_id, AppendMessageRequest(role="user", content="more"),
                db, _user(archived))
        await db.rollback()

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == conv_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_appending_to_a_live_conversation_still_works(archived):
    _, live_id, *_ = archived
    async with AsyncSessionLocal() as db:
        result = await append_message(
            live_id, AppendMessageRequest(role="user", content="hello"),
            db, _user(archived))
    assert result["message_count"] == 1


def test_the_endpoints_require_the_auditor_permission():
    """Export and purge are the auditor's job — AUDIT_READ is the permission
    Role.AUDITOR holds, and it does not carry the right to change the system."""
    import inspect

    from app.routers.conversations import export_conversations, purge_conversations

    for handler in (export_conversations, purge_conversations):
        assert "AUDIT_READ" in inspect.getsource(handler), handler.__name__


def test_purge_dry_runs_unless_confirmed():
    import inspect

    from app.routers.conversations import purge_conversations

    signature = inspect.signature(purge_conversations)
    assert signature.parameters["confirm"].default is False


@pytest.mark.asyncio
async def test_an_unconfigured_export_tells_the_operator_what_is_missing(monkeypatch):
    """The service raises a RuntimeError naming S3_ENDPOINT, but FastAPI turns
    an uncaught exception into a bare "Internal server error". The operator
    would be left guessing at the one thing that blocks the whole round —
    purge silently finding nothing eligible is the consequence of this.
    """
    from fastapi import HTTPException

    from app.routers.conversations import export_conversations

    from app.services.conversation_messages import append_messages_locked

    for var in ("S3_ENDPOINT", "OSS_ENDPOINT", "S3_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)

    # A conversation with a message: an empty one is skipped before S3 is
    # ever reached, so without this the test passes for the wrong reason on a
    # database other tests have cleaned out.
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"s3_{suffix}", email=f"s3_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, title="needs archiving")
        db.add(conv)
        await db.commit()
        await append_messages_locked(db, conv.id, [
            {"role": "user", "content": "something worth keeping"}])
        await db.commit()
        conv_id, user_id = conv.id, user.id

        try:
            with pytest.raises(HTTPException) as exc:
                await export_conversations(older_than_days=0, retain_days=365, db=db)
            assert exc.value.status_code == 503
            assert "S3_ENDPOINT" in exc.value.detail
        finally:
            await db.rollback()
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == conv_id))
            await db.execute(Conversation.__table__.delete().where(
                Conversation.id == conv_id))
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()
