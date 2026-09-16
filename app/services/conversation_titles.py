"""Titles that are a frozen UI placeholder rather than something a user chose.

Until 077f3c3 the chat client sent its own translated "New Chat" string as the
title of a new conversation, so whichever language was active at that moment
was written into the row. That is why an English UI could still show `新建对话`:
the column was not empty, so the client's localised fallback never ran.

The fix was to stop storing a placeholder. This clears the ones already stored.
A cleared row renders the caller's own translation and stays eligible for
auto-titling, which keys off the title being absent.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation

# Exact strings the clients have sent, in both languages and both wordings.
# Matched exactly (after trimming) so that a conversation someone deliberately
# named "New Chat with vendor" keeps its name.
PLACEHOLDER_TITLES: Sequence[str] = (
    "新对话",
    "新建对话",
    "New Chat",
    "New Conversation",
)


async def clear_placeholder_titles(session: AsyncSession) -> int:
    """Set such titles to NULL. Returns how many rows changed."""
    matches = or_(
        *[func.btrim(Conversation.title) == placeholder
          for placeholder in PLACEHOLDER_TITLES]
    )
    result = await session.execute(
        update(Conversation)
        .where(Conversation.title.is_not(None), matches)
        .values(title=None)
    )
    return result.rowcount or 0
