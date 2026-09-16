"""Appends land in the table, chained, at a cost that does not grow.

The blob this replaces made message n cost the size of messages 1..n-1. These
tests pin both halves of the fix: the chain is real, and the append is O(1).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, select

from app.core.database import AsyncSessionLocal, engine
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_chain import verify_conversation_chain
from app.services.conversation_messages import (
    append_messages_locked,
    fetch_messages,
    fetch_recent,
    to_llm_turns,
    to_message_dict,
)


@pytest.fixture
async def conv():
    """A user and an empty conversation, removed afterwards."""
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"msgstore_{suffix}", email=f"msgstore_{suffix}@example.test",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        row = Conversation(user_id=user.id, title="store")
        db.add(row)
        await db.commit()
        ids = (row.id, user.id)
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id == ids[0]))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id == ids[1]))
        await db.execute(User.__table__.delete().where(User.id == ids[1]))
        await db.commit()


async def _append(conv_id, *messages, user_id=None):
    async with AsyncSessionLocal() as db:
        result = await append_messages_locked(db, conv_id, list(messages), user_id=user_id)
        await db.commit()
        return result


@pytest.mark.asyncio
async def test_appending_writes_rows_with_a_dense_verifying_chain(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "scan it"},
                  {"role": "assistant", "content": "done"})

    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)

    assert [r.seq for r in rows] == [0, 1]
    assert [r.content for r in rows] == ["scan it", "done"]
    assert not any(r.backfilled for r in rows)
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_second_append_continues_the_same_chain(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "a"})
    _, count = await _append(conv_id, {"role": "assistant", "content": "b"})

    assert count == 2
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert rows[1].prev_hash == rows[0].entry_hash
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_the_stored_timestamp_is_what_the_hash_covers(conv):
    """The digest must be over the persisted datetime, not the caller's string,
    or nothing read back from the table would ever verify."""
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "x",
                            "created_at": "2026-09-01T10:00:00+00:00"})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert rows[0].created_at.tzinfo is None
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_message_with_no_content_is_stored_rather_than_dropped(conv):
    """A hole in the transcript is worse than an empty message in it."""
    conv_id, _ = conv
    await _append(conv_id, {"role": "assistant", "content": None})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert [r.content for r in rows] == [""]
    assert verify_conversation_chain(rows) is None


@pytest.mark.asyncio
async def test_a_wrong_owner_cannot_append(conv):
    conv_id, user_id = conv
    result, count = await _append(conv_id, {"role": "user", "content": "x"},
                                  user_id=user_id + 99999)
    assert result is None and count == 0


@pytest.mark.asyncio
async def test_an_unknown_conversation_appends_nothing(conv):
    result, count = await _append(2_000_000_000, {"role": "user", "content": "x"})
    assert result is None and count == 0


@pytest.mark.asyncio
async def test_an_empty_append_reports_the_count_without_writing(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "a"})
    _, count = await _append(conv_id)
    assert count == 1


# --- concurrency (spec 7.3) ---

@pytest.mark.asyncio
async def test_two_concurrent_appends_do_not_fork_the_chain(conv):
    """Two API workers appending at once must produce seq 0 and 1, never two
    rows at seq 0. The row lock serialises them; the unique constraint is the
    backstop if it ever does not.
    """
    import asyncio

    conv_id, _ = conv
    await asyncio.gather(
        _append(conv_id, {"role": "user", "content": "first"}),
        _append(conv_id, {"role": "user", "content": "second"}),
    )

    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)

    assert [r.seq for r in rows] == [0, 1]
    assert {r.content for r in rows} == {"first", "second"}
    assert verify_conversation_chain(rows) is None


# --- reads ---

@pytest.mark.asyncio
async def test_fetch_recent_returns_the_newest_in_reading_order(conv):
    conv_id, _ = conv
    await _append(conv_id, *[{"role": "user", "content": str(i)} for i in range(10)])
    async with AsyncSessionLocal() as db:
        rows = await fetch_recent(db, conv_id, 3)
    assert [r.content for r in rows] == ["7", "8", "9"]


@pytest.mark.asyncio
async def test_fetch_messages_pages_backwards_with_before_seq(conv):
    conv_id, _ = conv
    await _append(conv_id, *[{"role": "user", "content": str(i)} for i in range(10)])
    async with AsyncSessionLocal() as db:
        page = await fetch_messages(db, conv_id, limit=3, before_seq=5)
    assert [r.seq for r in page] == [2, 3, 4]


@pytest.mark.asyncio
async def test_to_llm_turns_drops_what_a_model_cannot_use(conv):
    conv_id, _ = conv
    await _append(conv_id,
                  {"role": "user", "content": "keep"},
                  {"role": "system", "content": "drop: not a turn"},
                  {"role": "assistant", "content": ""})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert to_llm_turns(rows) == [{"role": "user", "content": "keep"}]


@pytest.mark.asyncio
async def test_to_message_dict_keeps_the_shape_the_chat_client_expects(conv):
    conv_id, _ = conv
    await _append(conv_id, {"role": "user", "content": "hi"})
    async with AsyncSessionLocal() as db:
        rows = await fetch_messages(db, conv_id)
    assert set(to_message_dict(rows[0])) == {"role", "content", "created_at"}
    assert isinstance(to_message_dict(rows[0])["created_at"], str)


# --- cost (spec 7.6) ---

@pytest.mark.asyncio
async def test_appending_costs_the_same_at_message_500_as_at_message_1(conv):
    """The property the whole table exists for.

    Measured in statements issued and parameter bytes bound, not wall clock,
    so it does not flake on a loaded machine.
    """
    conv_id, _ = conv

    captured: list[tuple[str, int]] = []

    def record(_conn, _cursor, statement, parameters, _context, _executemany):
        captured.append((statement, len(str(parameters))))

    async def measure(target_conv_id):
        captured.clear()
        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            await _append(target_conv_id, {"role": "user", "content": "identical payload"})
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
        return len(captured), sum(size for _, size in captured)

    empty_statements, empty_bytes = await measure(conv_id)

    await _append(conv_id, *[{"role": "user", "content": "filler"} for _ in range(500)])
    long_statements, long_bytes = await measure(conv_id)

    assert long_statements == empty_statements, (
        f"appending to a long conversation issued {long_statements} statements "
        f"vs {empty_statements} to a short one - something scans the history"
    )
    # Not exactly equal: the bound parameters carry `seq`, so 501 renders two
    # characters wider than 0. That is the only growth permitted. The blob
    # behaviour this replaces would add ~500 messages' worth here, so a 64-byte
    # tolerance catches a regression with enormous margin while not flaking on
    # an integer getting longer.
    assert long_bytes - empty_bytes < 64, (
        f"the append wrote {long_bytes - empty_bytes} more bytes against a "
        "500-message history — it is scaling with the transcript, which is the "
        "blob behaviour this table replaces"
    )


@pytest.mark.asyncio
async def test_two_appends_on_one_session_do_not_collide(conv):
    """The session is built with autoflush=False, so without an explicit flush
    the second append's head query cannot see the first append's rows and both
    compute the same seq. uq_conv_messages_seq catches it — as it should — but
    a caller batching two appends before committing is an ordinary thing to do.
    """
    conv_id, _ = conv
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, conv_id, [{"role": "user", "content": "one"}])
        await append_messages_locked(db, conv_id, [{"role": "user", "content": "two"}])
        await db.commit()

        rows = await fetch_messages(db, conv_id)

    assert [r.seq for r in rows] == [0, 1]
    assert [r.content for r in rows] == ["one", "two"]
    assert verify_conversation_chain(rows) is None
