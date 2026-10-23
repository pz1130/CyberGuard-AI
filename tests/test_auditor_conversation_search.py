"""An auditor searching across everyone's conversations.

The self-service search is deliberately unable to do this: its owner comes
from the token and it takes no user_id, so it cannot be turned into an admin
endpoint by passing one. This is a separate endpoint, with the auditor's
permission, that can.

Two things it must see that ordinary search hides, and both are the point:

* **Conversations the user deleted.** Round 1 made delete a tombstone rather
  than a deletion precisely so a person cannot erase what the assistant told
  them. An auditor who could not see tombstones would make that pointless.
* **Internal agent memory slices.** Ordinary search excludes them because they
  are an agent's scratchpad, not something the person said. For an auditor
  they are the opposite: proving what the AI was working from is the job.

And the search itself is recorded. Reading someone's private conversations is
exactly the act that needs a trace, or "who watches the watchers" has no
answer here.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.time import utc_now
from app.models.agent import AgentConfig
from app.models.audit import AuditLog
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_messages import append_messages_locked
from app.services.message_search import search_messages


@pytest.fixture
async def world():
    """Two ordinary users plus an auditor. Amy has a live conversation, one she
    deleted, and an internal agent's memory slice. Bob has one of his own."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        amy = User(username=f"amy_{suffix}", email=f"amy_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        bob = User(username=f"bob_{suffix}", email=f"bob_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        auditor = User(username=f"aud_{suffix}", email=f"aud_{suffix}@company.local",
                       hashed_password="test-only", role="auditor", is_active=True)
        db.add_all([amy, bob, auditor])
        await db.flush()

        live = Conversation(user_id=amy.id, title="Amy live")
        gone = Conversation(user_id=amy.id, title="Amy deleted", deleted_at=utc_now())
        slice_ = Conversation(user_id=amy.id, title="agent:recon")
        bobs = Conversation(user_id=bob.id, title="Bob live")
        db.add_all([live, gone, slice_, bobs])
        await db.flush()

        agent = AgentConfig(agent_name=f"recon_{suffix}", backend_type="__internal__")
        db.add(agent)
        await db.flush()
        slice_.agent_id = agent.id
        slice_.parent_conversation_id = live.id
        await db.commit()

        for conv_id, text in [
            (live.id, "端口 amy live"),
            (gone.id, "端口 amy deleted"),
            (slice_.id, "端口 agent scratchpad"),
            (bobs.id, "端口 bob live"),
        ]:
            await append_messages_locked(db, conv_id, [{"role": "user", "content": text}])
        await db.commit()

        ids = dict(amy=amy.id, bob=bob.id, auditor=auditor.id,
                   auditor_name=auditor.username, auditor_email=auditor.email,
                   live=live.id, gone=gone.id, slice=slice_.id, bobs=bobs.id,
                   agent=agent.id)
    yield ids
    async with AsyncSessionLocal() as db:
        convs = [ids["live"], ids["gone"], ids["slice"], ids["bobs"]]
        await db.execute(AuditLog.__table__.delete().where(
            AuditLog.user_id == ids["auditor"]))
        await db.execute(ConversationMessage.__table__.delete().where(
            ConversationMessage.conversation_id.in_(convs)))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id.in_([ids["amy"], ids["bob"]])))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids["amy"], ids["bob"], ids["auditor"]])))
        await db.execute(AgentConfig.__table__.delete().where(
            AgentConfig.id == ids["agent"]))
        await db.commit()


def _auditor(world):
    return AuthenticatedUser(user_id=world["auditor"], username=world["auditor_name"],
                             email=world["auditor_email"], role="auditor")


async def _audit_search(world, **kw):
    from app.routers.audit import auditor_conversation_search

    async with AsyncSessionLocal() as db:
        return await auditor_conversation_search(
            q=kw.get("q", "端口"), user_id=kw.get("user_id"),
            limit=kw.get("limit", 20), cursor=kw.get("cursor"),
            db=db, current_user=_auditor(world))


def _conv_ids(payload):
    return {r["conversation_id"] for r in payload["results"]}


# --- the service gains a scope, without losing the old one ---

@pytest.mark.asyncio
async def test_no_owner_filter_reaches_every_user(world):
    async with AsyncSessionLocal() as db:
        hits = await search_messages(db, user_id=None, term="端口",
                                     include_hidden=True, limit=50)
    found = {h.conversation_id for h in hits}
    assert {world["live"], world["bobs"]} <= found


@pytest.mark.asyncio
async def test_self_service_search_is_unchanged(world):
    """The default must still be one user, live conversations, no agent slices."""
    async with AsyncSessionLocal() as db:
        hits = await search_messages(db, user_id=world["amy"], term="端口")
    assert {h.conversation_id for h in hits} == {world["live"]}


# --- what the auditor can see that a person cannot ---

@pytest.mark.asyncio
async def test_an_auditor_sees_another_users_messages(world):
    payload = await _audit_search(world)
    assert world["bobs"] in _conv_ids(payload)


@pytest.mark.asyncio
async def test_an_auditor_sees_a_conversation_the_user_deleted(world):
    """Round 1 made delete a tombstone so a person cannot erase what the
    assistant told them. An auditor blind to tombstones makes that pointless."""
    assert world["gone"] in _conv_ids(await _audit_search(world))


@pytest.mark.asyncio
async def test_an_auditor_sees_an_agent_memory_slice(world):
    """Proving what the AI was working from is the job."""
    assert world["slice"] in _conv_ids(await _audit_search(world))


@pytest.mark.asyncio
async def test_scoping_to_one_user_excludes_the_others(world):
    payload = await _audit_search(world, user_id=world["bob"])
    assert _conv_ids(payload) == {world["bobs"]}


# --- the search is itself recorded ---

@pytest.mark.asyncio
async def test_the_search_is_audited(world):
    await _audit_search(world, q="端口")
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["auditor"],
            AuditLog.action == "audit.conversation_search"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].entry_hash and rows[0].prev_hash


@pytest.mark.asyncio
async def test_an_empty_query_is_rejected_and_not_audited(world):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _audit_search(world, q="   ")
    assert exc.value.status_code == 400

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AuditLog).where(
            AuditLog.user_id == world["auditor"],
            AuditLog.action == "audit.conversation_search"))).scalars().all()
    assert rows == [], "a rejected search is not a search"


# --- the permission boundary ---

def test_the_endpoint_requires_the_auditor_permission():
    import inspect

    from app.routers.audit import auditor_conversation_search

    assert "AUDIT_READ" in inspect.getsource(auditor_conversation_search)


def test_the_self_service_endpoint_still_refuses_a_user_id():
    """Round 2's guarantee must survive this change: the self-service search
    cannot be turned into an admin endpoint by passing a parameter."""
    import inspect

    from app.routers.conversations import search_conversation_messages

    assert "user_id" not in inspect.signature(search_conversation_messages).parameters


# --- whose conversation is it ---

@pytest.mark.asyncio
async def test_results_name_the_owner(world):
    """A cross-user search that does not say whose conversation it found is
    most of the way to useless: the auditor's next question is always "who".
    """
    payload = await _audit_search(world)
    by_conv = {r["conversation_id"]: r for r in payload["results"]}

    assert by_conv[world["bobs"]]["user_id"] == world["bob"]
    assert by_conv[world["bobs"]]["username"].startswith("bob_")
    assert by_conv[world["live"]]["user_id"] == world["amy"]
    assert by_conv[world["live"]]["username"].startswith("amy_")


@pytest.mark.asyncio
async def test_every_result_names_an_owner(world):
    """There is no such thing as an ownerless conversation here:
    conversations.user_id is NOT NULL and its foreign key has neither CASCADE
    nor SET NULL, so a user who owns one cannot be deleted at all. The grouping
    in the UI relies on that — every row has a user to sit under.
    """
    payload = await _audit_search(world)
    assert payload["results"], "expected hits"
    for row in payload["results"]:
        assert row["user_id"] is not None, row
        assert row["username"], row
