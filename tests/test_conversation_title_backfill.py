"""Migration 042: clear titles that are a frozen placeholder, not a name.

Until 077f3c3 the client sent its own translated "New Chat" string as the title
when creating a conversation, so whichever language happened to be active got
written into the row. 040 stopped the database handing out `'新对话'` by
default, but neither change touched rows that already existed — which is why an
English UI still showed `新建对话` in the sidebar: the title was not empty, so
the client's localised fallback never ran.

Clearing them to NULL is what makes `conv.title || t('chat.newChat')` work, and
auto-titling keys off absence too, so a cleared row can still earn a real name.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.user import User
from app.services.conversation_titles import PLACEHOLDER_TITLES, clear_placeholder_titles


def test_every_placeholder_the_clients_have_ever_sent_is_covered():
    """Both languages, both the old and current wording."""
    assert {"新对话", "新建对话", "New Chat", "New Conversation"} <= set(PLACEHOLDER_TITLES)


def test_the_comparison_is_exact_not_a_prefix():
    """A conversation a user deliberately named "New Chat with vendor" is a
    real title and must survive."""
    assert "New Chat with vendor" not in PLACEHOLDER_TITLES


@pytest.mark.asyncio
async def test_placeholder_titles_are_cleared_and_real_ones_are_kept():
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(username=f"title_{suffix}", email=f"title_{suffix}@example.com",
                    hashed_password="test-only", role="admin", is_active=True)
        db.add(user)
        await db.flush()

        rows = {
            "zh_new": "新建对话",
            "zh_old": "新对话",
            "en": "New Chat",
            "padded": "  新建对话  ",
            "real": "Port scan triage",
            "lookalike": "New Chat with vendor",
        }
        created = {}
        for key, title in rows.items():
            conv = Conversation(user_id=user.id, title=title)
            db.add(conv)
            await db.flush()
            created[key] = conv.id
        await db.commit()
        user_id = user.id

        try:
            cleared = await clear_placeholder_titles(db)
            await db.commit()
            assert cleared >= 4

            titles = {}
            for key, cid in created.items():
                conv = (await db.execute(select(Conversation).where(
                    Conversation.id == cid))).scalar_one()
                await db.refresh(conv)
                titles[key] = conv.title

            assert titles["zh_new"] is None
            assert titles["zh_old"] is None
            assert titles["en"] is None
            assert titles["padded"] is None, "whitespace must not smuggle one through"
            assert titles["real"] == "Port scan triage"
            assert titles["lookalike"] == "New Chat with vendor"
        finally:
            await db.execute(text(
                "DELETE FROM conversations WHERE user_id = :uid"), {"uid": user_id})
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()


@pytest.mark.asyncio
async def test_running_it_twice_changes_nothing_the_second_time():
    """It ships as a migration, but an operator may also run it by hand."""
    async with AsyncSessionLocal() as db:
        await clear_placeholder_titles(db)
        await db.commit()
        assert await clear_placeholder_titles(db) == 0
        await db.commit()
