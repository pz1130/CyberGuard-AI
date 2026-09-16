"""A deleted user must not be able to take the API down.

The HTTP middleware buffers an audit entry per request, carrying the actor's
user id. Deleting that user between the buffering and the flush made the
insert violate audit_logs_user_id_fkey — and `_flush_audit_buffer` puts failed
entries back at the head of the buffer and re-raises, by design, so nothing is
lost. For an entry that can *never* succeed that turned "lose one audit row"
into "every subsequent request 500s until the process restarts".

Observed on the running deployment: three consecutive logins returned 500 and
it did not recover.

The column's foreign key is already `ON DELETE SET NULL`, so a row that was
already stored loses its actor when the user goes. This applies the same
settled policy to a row still in the buffer, rather than inventing one.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core import audit as audit_mod
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.user import User


@pytest.fixture(autouse=True)
async def empty_buffer():
    """The buffer is module-global; leaving entries in it breaks later tests."""
    async with audit_mod._buffer_lock:
        audit_mod._audit_buffer.clear()
    yield
    async with audit_mod._buffer_lock:
        audit_mod._audit_buffer.clear()


@pytest.fixture
async def doomed_user():
    """A user who exists long enough to act, then does not."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"gone_{suffix}", email=f"gone_{suffix}@company.local",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.commit()
        user_id = user.id
    yield user_id
    async with AsyncSessionLocal() as db:
        await db.execute(AuditLog.__table__.delete().where(
            AuditLog.action == f"test.orphan.{user_id}"))
        await db.execute(User.__table__.delete().where(User.id == user_id))
        await db.commit()


async def _delete(user_id):
    async with AsyncSessionLocal() as db:
        await db.execute(User.__table__.delete().where(User.id == user_id))
        await db.commit()


async def _rows(action):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(AuditLog).where(
            AuditLog.action == action))).scalars().all()


@pytest.mark.asyncio
async def test_a_flush_survives_an_actor_who_was_deleted(doomed_user):
    action = f"test.orphan.{doomed_user}"
    await audit_mod.log_audit(
        user_id=doomed_user, agent_id=None, action=action,
        input_data={"method": "POST"}, output_data={"status": 200},
        ip_address="10.0.0.9", request_path="/api/v1/auth/login")

    await _delete(doomed_user)
    await audit_mod.flush_audit_buffer()   # must not raise

    rows = await _rows(action)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_the_entry_keeps_everything_except_the_actor(doomed_user):
    """The actor is the only thing the deletion took. What happened, from
    where, and against which path are what an investigator filters on."""
    action = f"test.orphan.{doomed_user}"
    await audit_mod.log_audit(
        user_id=doomed_user, agent_id=None, action=action,
        input_data={"method": "POST"}, output_data={"status": 200},
        ip_address="10.0.0.9", request_path="/api/v1/auth/login")
    await _delete(doomed_user)
    await audit_mod.flush_audit_buffer()

    row = (await _rows(action))[0]
    assert row.user_id is None
    assert row.ip_address == "10.0.0.9"
    assert row.request_path == "/api/v1/auth/login"
    assert row.input_hash and row.output_hash


@pytest.mark.asyncio
async def test_the_row_still_verifies_against_its_own_hash(doomed_user):
    """The actor must be cleared before the chain payload is built, or the
    stored row would not match the hash stored beside it."""
    action = f"test.orphan.{doomed_user}"
    await audit_mod.log_audit(
        user_id=doomed_user, agent_id=None, action=action,
        input_data={"a": 1}, output_data={"b": 2})
    await _delete(doomed_user)
    await audit_mod.flush_audit_buffer()

    row = (await _rows(action))[0]
    recomputed = audit_mod.stamp_chain_hashes(
        audit_mod._row_chain_payload(row), row.prev_hash)
    assert recomputed["entry_hash"] == row.entry_hash


@pytest.mark.asyncio
async def test_a_surviving_actor_is_left_alone(doomed_user):
    """Clearing must be surgical: one dead actor must not blank the others."""
    action = f"test.orphan.{doomed_user}"
    async with AsyncSessionLocal() as db:
        keeper = User(username=f"keep_{uuid.uuid4().hex[:8]}",
                      email=f"keep_{uuid.uuid4().hex[:8]}@company.local",
                      hashed_password="test-only", role="admin", is_active=True)
        db.add(keeper)
        await db.commit()
        keeper_id = keeper.id

    try:
        await audit_mod.log_audit(user_id=doomed_user, agent_id=None, action=action,
                                  input_data={}, output_data={})
        await audit_mod.log_audit(user_id=keeper_id, agent_id=None, action=action,
                                  input_data={}, output_data={})
        await _delete(doomed_user)
        await audit_mod.flush_audit_buffer()

        actors = sorted(r.user_id or 0 for r in await _rows(action))
        assert actors == [0, keeper_id]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(AuditLog.__table__.delete().where(
                AuditLog.action == action))
            await db.execute(User.__table__.delete().where(User.id == keeper_id))
            await db.commit()


@pytest.mark.asyncio
async def test_the_buffer_is_emptied_rather_than_re_queued(doomed_user):
    """The poisoning was the re-queue: a permanently failing entry was retried
    on every later flush, so each one failed too."""
    action = f"test.orphan.{doomed_user}"
    await audit_mod.log_audit(user_id=doomed_user, agent_id=None, action=action,
                              input_data={}, output_data={})
    await _delete(doomed_user)
    await audit_mod.flush_audit_buffer()

    async with audit_mod._buffer_lock:
        assert audit_mod._audit_buffer == []

    # And a later, unrelated flush is unaffected.
    await audit_mod.flush_audit_buffer()
