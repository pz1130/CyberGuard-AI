"""Searching your own chat history.

The permission boundary is the test that matters most here: a search that can
reach another user's messages is a data breach, not a bug. It is asserted
against two seeded users rather than by reading the code.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.agent import AgentConfig
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.conversation_messages import append_messages_locked
from app.services.message_search import escape_like, search_messages


@pytest.fixture
async def world():
    """Two users. Amy has an ordinary conversation, a deleted one, and an
    internal agent's memory slice. Bob has one conversation of his own."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        amy = User(username=f"amy_{suffix}", email=f"amy_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        bob = User(username=f"bob_{suffix}", email=f"bob_{suffix}@company.local",
                   hashed_password="test-only", role="admin", is_active=True)
        db.add_all([amy, bob])
        await db.flush()

        live = Conversation(user_id=amy.id, title="Port scan triage")
        gone = Conversation(user_id=amy.id, title="Deleted work")
        slice_ = Conversation(user_id=amy.id, title="agent:recon")
        bobs = Conversation(user_id=bob.id, title="Bob's own")
        db.add_all([live, gone, slice_, bobs])
        await db.flush()

        # agent_id is what makes a row an internal agent's memory rather than a
        # conversation. It is a foreign key, so the slice needs a real agent.
        # agent_name and backend_type are AgentConfig's only required columns.
        agent = AgentConfig(agent_name=f"recon_{suffix}", backend_type="__internal__")
        db.add(agent)
        await db.flush()
        slice_.agent_id = agent.id
        slice_.parent_conversation_id = live.id
        await db.commit()

        await append_messages_locked(db, live.id, [
            {"role": "user", "content": "扫描主机的开放端口"},
            {"role": "assistant", "content": "three open ports, including 22/tcp"},
            {"role": "assistant", "content": "utilisation reached 100% briefly"},
            {"role": "user", "content": "check a_b naming"},
        ])
        await append_messages_locked(db, gone.id, [
            {"role": "user", "content": "端口 in a conversation that gets deleted"}])
        await append_messages_locked(db, bobs.id, [
            {"role": "user", "content": "端口 belonging to Bob"}])
        await append_messages_locked(db, slice_.id, [
            {"role": "assistant", "content": "端口 internal agent reasoning"}])
        await db.commit()

        ids = dict(amy=amy.id, bob=bob.id, live=live.id, gone=gone.id,
                   slice=slice_.id, bobs=bobs.id, agent=agent.id)
    yield ids
    async with AsyncSessionLocal() as db:
        for cid in (ids["live"], ids["gone"], ids["slice"], ids["bobs"]):
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == cid))
        await db.execute(Conversation.__table__.delete().where(
            Conversation.user_id.in_([ids["amy"], ids["bob"]])))
        await db.execute(User.__table__.delete().where(
            User.id.in_([ids["amy"], ids["bob"]])))
        await db.execute(AgentConfig.__table__.delete().where(
            AgentConfig.id == ids["agent"]))
        await db.commit()


async def _search(user_id, term, **kw):
    async with AsyncSessionLocal() as db:
        return await search_messages(db, user_id=user_id, term=term, **kw)


# --- correctness ---

@pytest.mark.asyncio
async def test_an_english_term_finds_its_message(world):
    hits = await _search(world["amy"], "open ports")
    assert [m.content for h in hits for m in h.matches] == [
        "three open ports, including 22/tcp"]


@pytest.mark.asyncio
async def test_a_two_character_chinese_term_finds_its_message(world):
    """The case the trigram index cannot accelerate. It must still be correct —
    the index is a speed decision, never a correctness one."""
    hits = await _search(world["amy"], "端口")
    assert any("开放端口" in m.content for h in hits for m in h.matches)


@pytest.mark.asyncio
async def test_results_carry_the_conversation_they_belong_to(world):
    hits = await _search(world["amy"], "open ports")
    assert hits[0].conversation_id == world["live"]
    assert hits[0].conversation_title == "Port scan triage"


# --- the permission boundary ---

@pytest.mark.asyncio
async def test_a_search_never_reaches_another_users_messages(world):
    """The one that matters. Bob's message contains the term; Amy must not see it."""
    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["bobs"] for h in hits)
    assert all("Bob" not in m.content for h in hits for m in h.matches)


@pytest.mark.asyncio
async def test_each_user_sees_only_their_own(world):
    bob_hits = await _search(world["bob"], "端口")
    assert len(bob_hits) == 1
    assert bob_hits[0].conversation_id == world["bobs"]


# --- tombstones ---

@pytest.mark.asyncio
async def test_a_deleted_conversations_messages_are_not_returned(world):
    from app.core.time import utc_now

    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, world["gone"])
        conv.deleted_at = utc_now()
        await db.commit()

    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["gone"] for h in hits)

    async with AsyncSessionLocal() as db:
        surviving = (await db.execute(select(ConversationMessage).where(
            ConversationMessage.conversation_id == world["gone"]))).scalars().all()
    assert len(surviving) == 1, "Round 1's immutability must not be weakened"


@pytest.mark.asyncio
async def test_an_agent_memory_slice_is_never_searched(world):
    """The slice is a conversations row owned by the searching user, holding an
    internal agent's working memory. Searching your chat history means the
    conversations you had."""
    hits = await _search(world["amy"], "端口")
    assert all(h.conversation_id != world["slice"] for h in hits)


# --- escaping ---

def test_escape_like_neutralises_wildcards():
    assert escape_like("100%") == r"100\%"
    assert escape_like("a_b") == r"a\_b"
    assert escape_like(r"back\slash") == r"back\\slash"


@pytest.mark.asyncio
async def test_a_percent_sign_is_a_literal_not_a_wildcard(world):
    hits = await _search(world["amy"], "100%")
    assert len(hits) == 1
    assert "100%" in hits[0].matches[0].content


@pytest.mark.asyncio
async def test_an_underscore_is_a_literal_not_a_single_character_wildcard(world):
    assert len(await _search(world["amy"], "a_b")) == 1
    assert await _search(world["amy"], "axb") == []


# --- paging ---

@pytest.mark.asyncio
async def test_paging_returns_each_hit_once(world):
    first = await _search(world["amy"], "e", limit=2)
    assert len(first) == 2
    second = await _search(world["amy"], "e", limit=2,
                           cursor=first[-1].matches[0].message_id)
    ids = [h.conversation_id for h in first] + [h.conversation_id for h in second]
    assert len(ids) == len(set(ids)), "a message appeared on two pages"


@pytest.mark.asyncio
async def test_results_are_newest_first(world):
    hits = await _search(world["amy"], "e", limit=10)
    newest = [h.matches[0].message_id for h in hits]
    assert newest == sorted(newest, reverse=True)


@pytest.mark.asyncio
async def test_the_limit_is_capped(world):
    from app.services.message_search import MAX_SEARCH_LIMIT

    hits = await _search(world["amy"], "e", limit=10_000)
    assert len(hits) <= MAX_SEARCH_LIMIT


# --- the endpoint ---

@pytest.mark.asyncio
async def test_the_endpoint_returns_snippets_not_message_bodies(world):
    from app.routers.conversations import search_conversation_messages

    amy = AuthenticatedUser(user_id=world["amy"], username="amy",
                            email="amy@company.local", role="admin")
    async with AsyncSessionLocal() as db:
        payload = await search_conversation_messages("open ports", 20, None, db, amy)

    assert payload["results"], "expected a hit"
    result = payload["results"][0]
    assert set(result) == {"conversation_id", "conversation_title", "user_id",
                           "username", "hits", "matches"}
    assert set(result["matches"][0]) == {
        "message_id", "seq", "role", "created_at", "snippet"}, (
        "an exact set, so a future change that starts returning message bodies "
        "shows up here")


@pytest.mark.asyncio
async def test_an_empty_query_is_rejected(world):
    from fastapi import HTTPException

    from app.routers.conversations import search_conversation_messages

    amy = AuthenticatedUser(user_id=world["amy"], username="amy",
                            email="amy@company.local", role="admin")
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc:
            await search_conversation_messages("   ", 20, None, db, amy)
    assert exc.value.status_code == 400


def test_the_search_route_is_declared_before_the_conversation_id_route():
    """FastAPI matches in declaration order. Declared after, /conversations/
    search binds to {conv_id}, fails int parsing and 422s — with no test
    failing anywhere else to explain why."""
    import inspect

    from app.routers import conversations as module

    src = inspect.getsource(module)
    assert src.index('"/conversations/search"') < src.index('"/conversations/{conv_id}"')


def test_the_endpoint_takes_the_user_from_the_token_only():
    """A user_id parameter would make this an admin endpoint wearing a
    self-service name."""
    import inspect

    from app.routers.conversations import search_conversation_messages

    assert "user_id" not in inspect.signature(search_conversation_messages).parameters
    assert "current_user.user_id" in inspect.getsource(search_conversation_messages)


# --- one row per conversation (collapsing) ---

@pytest.mark.asyncio
async def test_a_conversation_appears_once_however_many_messages_match(world):
    """Searching returns conversations, not messages. "端口" matches two
    messages in the same conversation; listing it twice is noise, and it made
    `limit` mean something the reader did not ask for."""
    hits = await _search(world["amy"], "e")
    conversation_ids = [h.conversation_id for h in hits]
    assert len(conversation_ids) == len(set(conversation_ids))


@pytest.mark.asyncio
async def test_the_hit_count_says_how_many_messages_matched(world):
    """Collapsing must not hide how much there is — that is the number a
    person uses to decide whether to open it."""
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, world["live"], [
            {"role": "user", "content": "端口 again"},
            {"role": "user", "content": "端口 once more"},
        ])
        await db.commit()

    hits = await _search(world["amy"], "端口")
    live = next(h for h in hits if h.conversation_id == world["live"])
    assert live.hits == 3, "one original plus the two just appended"


@pytest.mark.asyncio
async def test_the_first_match_is_the_newest_one(world):
    """Newest first is what "find that thing I said" means."""
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, world["live"], [
            {"role": "assistant", "content": "端口 the latest word on it"}])
        await db.commit()

    hits = await _search(world["amy"], "端口")
    live = next(h for h in hits if h.conversation_id == world["live"])
    assert live.matches[0].content == "端口 the latest word on it"


@pytest.mark.asyncio
async def test_a_conversation_carries_its_matching_messages(world):
    """Collapsing must not cost the reader the matches themselves. Showing one
    line for a conversation with three hits is what made the results look
    incomplete."""
    async with AsyncSessionLocal() as db:
        await append_messages_locked(db, world["live"], [
            {"role": "user", "content": "端口 second"},
            {"role": "user", "content": "端口 third"},
        ])
        await db.commit()

    hits = await _search(world["amy"], "端口")
    live = next(h for h in hits if h.conversation_id == world["live"])
    assert live.hits == 3
    assert len(live.matches) == 3
    assert [m.content for m in live.matches] == [
        "端口 third", "端口 second", "扫描主机的开放端口"]


@pytest.mark.asyncio
async def test_the_matches_per_conversation_are_capped(world):
    """A conversation with fifty hits must not flood the page; the count still
    says how many there are."""
    from app.services.message_search import MAX_MATCHES_PER_CONVERSATION

    async with AsyncSessionLocal() as db:
        for i in range(6):
            await append_messages_locked(db, world["live"], [
                {"role": "user", "content": f"端口 filler {i}"}])
        await db.commit()

    hits = await _search(world["amy"], "端口")
    live = next(h for h in hits if h.conversation_id == world["live"])
    assert live.hits == 7
    assert len(live.matches) == MAX_MATCHES_PER_CONVERSATION


@pytest.mark.asyncio
async def test_limit_now_counts_conversations(world):
    async with AsyncSessionLocal() as db:
        for _ in range(4):
            await append_messages_locked(db, world["live"], [
                {"role": "user", "content": "端口 filler"}])
        await db.commit()

    assert len(await _search(world["amy"], "端口", limit=1)) == 1


@pytest.mark.asyncio
async def test_paging_walks_conversations_without_repeating_one(world):
    """The cursor is the representative id, and a conversation's representative
    is its newest match — so a page boundary cannot re-surface a conversation
    through an older message."""
    async with AsyncSessionLocal() as db:
        second = Conversation(user_id=world["amy"], title="Another")
        db.add(second)
        await db.commit()
        await append_messages_locked(db, second.id, [
            {"role": "user", "content": "端口 elsewhere"}])
        await db.commit()
        second_id = second.id

    try:
        first_page = await _search(world["amy"], "端口", limit=1)
        assert len(first_page) == 1
        rest = await _search(world["amy"], "端口", limit=5,
                             cursor=first_page[-1].matches[0].message_id)
        seen = [h.conversation_id for h in first_page + rest]
        assert len(seen) == len(set(seen)), "a conversation appeared on two pages"
        assert second_id in seen
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(ConversationMessage.__table__.delete().where(
                ConversationMessage.conversation_id == second_id))
            await db.execute(Conversation.__table__.delete().where(
                Conversation.id == second_id))
            await db.commit()
