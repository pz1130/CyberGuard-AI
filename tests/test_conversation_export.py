"""Mirroring a conversation to write-once storage.

The object has to be verifiable on its own: a reader with nothing but the file
should be able to recompute the chain and compare its head against the
`conversation.chain_anchor` row in the exported audit log. That is why the
export carries every field the hash covers, and why a conversation whose chain
does not verify is never written — putting a known-corrupt chain into immutable
storage makes the corruption permanent and gives it the look of evidence.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.conversation_export import ConversationExport
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services import conversation_export as ce
from app.services.conversation_chain import verify_conversation_chain
from app.services.conversation_messages import append_messages_locked


@pytest.fixture
async def world():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"exp_{suffix}", email=f"exp_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        full = Conversation(user_id=user.id, title="Port scan triage")
        empty = Conversation(user_id=user.id, title="Nothing said")
        db.add_all([full, empty])
        await db.commit()

        await append_messages_locked(db, full.id, [
            {"role": "user", "content": "扫描主机的开放端口"},
            {"role": "assistant", "content": "three open ports"},
        ])
        await db.commit()
        ids = dict(user=user.id, full=full.id, empty=empty.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationExport.__table__.delete().where(
            ConversationExport.conversation_id.in_([ids["full"], ids["empty"]])))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_([ids["full"], ids["empty"]])))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids["user"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.commit()


async def _export(conversation_id, **kw):
    """Export with the upload mocked, returning (summary, uploaded_body)."""
    captured = {}

    async def fake_put(key, data, retain_until):
        captured["key"] = key
        captured["body"] = data.decode()
        return key

    with patch.object(ce, "_put_worm_object", AsyncMock(side_effect=fake_put)):
        async with AsyncSessionLocal() as db:
            summary = await ce.export_conversation(
                db, conversation_id, retain_days=kw.get("retain_days", 365))
            await db.commit()
    return summary, captured


# --- the object ---

@pytest.mark.asyncio
async def test_every_message_is_exported_in_order(world):
    summary, captured = await _export(world["full"])
    lines = [json.loads(line) for line in captured["body"].splitlines()]
    messages = [line for line in lines if line["type"] == "message"]

    assert summary["rows"] == 2
    assert [m["seq"] for m in messages] == [0, 1]
    assert messages[0]["content"] == "扫描主机的开放端口"


@pytest.mark.asyncio
async def test_the_object_carries_the_conversation_itself(world):
    _, captured = await _export(world["full"])
    header = json.loads(captured["body"].splitlines()[0])
    assert header["type"] == "conversation"
    assert header["id"] == world["full"]
    assert header["title"] == "Port scan triage"


@pytest.mark.asyncio
async def test_the_chain_can_be_recomputed_from_the_object_alone(world):
    """The property that makes an export evidence rather than a copy."""
    _, captured = await _export(world["full"])
    rebuilt = [
        SimpleNamespace(**{k: v for k, v in json.loads(line).items() if k != "type"})
        for line in captured["body"].splitlines()
        if json.loads(line)["type"] == "message"
    ]
    # conversation_id is on the header line, not each message; created_at is
    # already the ISO string the hash was computed over, and
    # conversation_chain._iso passes a string through unchanged.
    for row in rebuilt:
        row.conversation_id = world["full"]
    assert verify_conversation_chain(rebuilt) is None


@pytest.mark.asyncio
async def test_the_recorded_head_matches_the_conversations_last_message(world):
    summary, _ = await _export(world["full"])
    async with AsyncSessionLocal() as db:
        head = (await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == world["full"])
            .order_by(ConversationMessage.seq.desc()).limit(1))).scalar_one()
    assert summary["head_seq"] == head.seq
    assert summary["head_hash"] == head.entry_hash


@pytest.mark.asyncio
async def test_the_export_is_recorded(world):
    summary, _ = await _export(world["full"])
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == world["full"]))).scalar_one()
    assert row.object_key == summary["object_key"]
    assert row.rows == 2 and row.head_seq == 1


# --- refusals ---

@pytest.mark.asyncio
async def test_an_empty_conversation_is_skipped(world):
    summary, captured = await _export(world["empty"])
    assert summary["skipped"] == "empty"
    assert "body" not in captured, "nothing should have been uploaded"


@pytest.mark.asyncio
async def test_a_broken_chain_is_reported_and_never_uploaded(world):
    """Writing a known-corrupt chain into immutable storage would make the
    corruption permanent and give it the appearance of evidence."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE conversation_messages SET content = 'tampered' "
            "WHERE conversation_id = :cid AND seq = 0"), {"cid": world["full"]})
        await db.commit()

    summary, captured = await _export(world["full"])
    assert summary["skipped"].startswith("chain-broken")
    assert "body" not in captured, "a corrupt conversation must not be uploaded"

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ConversationExport).where(
            ConversationExport.conversation_id == world["full"]))).scalars().all()
    assert rows == [], "no export may be recorded for a corrupt conversation"


@pytest.mark.asyncio
async def test_one_failure_does_not_stop_the_others(world):
    """export_eligible processes a batch; a single bad conversation must not
    cost the rest their archive."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "UPDATE conversation_messages SET content = 'tampered' "
            "WHERE conversation_id = :cid AND seq = 0"), {"cid": world["full"]})
        await db.commit()

    async def fake_put(key, data, retain_until):
        return key

    with patch.object(ce, "_put_worm_object", AsyncMock(side_effect=fake_put)):
        async with AsyncSessionLocal() as db:
            summary = await ce.export_eligible(db, older_than_days=0, retain_days=365)
            await db.commit()

    reported = {s["conversation_id"] for s in summary["skipped"]}
    assert world["full"] in reported
    assert world["empty"] in reported


# --- the operability constraint ---

@pytest.mark.asyncio
async def test_export_fails_loudly_when_s3_is_unconfigured(world, monkeypatch):
    """Every deployment here is in this state. The failure must name what is
    missing, because purge silently finding nothing eligible is the
    consequence."""
    for var in ("S3_ENDPOINT", "OSS_ENDPOINT", "S3_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)

    async with AsyncSessionLocal() as db:
        with pytest.raises(RuntimeError) as exc:
            await ce.export_conversation(db, world["full"], retain_days=365)
    assert "S3_ENDPOINT" in str(exc.value)
