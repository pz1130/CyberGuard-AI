"""Keyword search over chat messages, scoped to one owner.

Matching is ``ILIKE`` over a ``pg_trgm`` index rather than full-text search:
PostgreSQL tokenises a whole Chinese sentence as one lexeme, so a tsvector
cannot match a keyword inside one (see the Round 2 design).

``user_id`` is a parameter rather than something this module reads from a
token, so the auditor path can pass a different scope without the search being
rewritten. The caller is responsible for deciding whose messages these are;
this module is responsible for honouring that decision. ``None`` means every
user, which only the auditor endpoint passes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

_LIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class SearchHit:
    conversation_id: int
    conversation_title: Optional[str]
    message_id: int
    seq: int
    role: str
    content: str
    created_at: datetime


def escape_like(term: str) -> str:
    """Neutralise LIKE wildcards in a user's query.

    Without this, searching ``100%`` matches every message and ``a_b`` matches
    ``axb``. The backslash goes first, or it would escape the escapes.
    """
    return (
        term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


async def search_messages(
    session: AsyncSession,
    *,
    user_id: Optional[int],
    term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    cursor: Optional[int] = None,
    include_hidden: bool = False,
) -> List[SearchHit]:
    """Messages containing ``term``, newest first.

    ``user_id=None`` searches every user; only the auditor endpoint passes it.

    ``include_hidden`` admits the two kinds of conversation ordinary search
    excludes — ones the person deleted, and internal-agent memory slices. They
    travel together because no caller wants one without the other: a person
    should see neither, and an auditor needs both. Tombstones are why Round 1
    made delete not delete, and a slice is where an agent's own reasoning is.

    The predicates live here rather than being left to the partial index: the
    index is an optimisation and must never be the security boundary.
    """
    pattern = f"%{escape_like(term)}%"
    conditions = [ConversationMessage.content.ilike(pattern, escape=_LIKE_ESCAPE)]
    if user_id is not None:
        conditions.append(Conversation.user_id == user_id)
    if not include_hidden:
        conditions.append(Conversation.deleted_at.is_(None))
        conditions.append(Conversation.agent_id.is_(None))

    stmt = (
        select(
            ConversationMessage.conversation_id,
            Conversation.title,
            ConversationMessage.id,
            ConversationMessage.seq,
            ConversationMessage.role,
            ConversationMessage.content,
            ConversationMessage.created_at,
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(*conditions)
        .order_by(ConversationMessage.id.desc())
        .limit(max(1, min(int(limit), MAX_SEARCH_LIMIT)))
    )
    if cursor is not None:
        stmt = stmt.where(ConversationMessage.id < cursor)

    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(
            conversation_id=row[0], conversation_title=row[1], message_id=row[2],
            seq=row[3], role=row[4], content=row[5], created_at=row[6],
        )
        for row in rows
    ]
