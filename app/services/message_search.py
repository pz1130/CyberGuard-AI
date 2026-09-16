"""Keyword search over chat messages, scoped to one owner.

Matching is ``ILIKE`` over a ``pg_trgm`` index rather than full-text search:
PostgreSQL tokenises a whole Chinese sentence as one lexeme, so a tsvector
cannot match a keyword inside one (see the Round 2 design).

``user_id`` is a parameter rather than something this module reads from a
token, so the Round 3 auditor path can pass a different scope without the
search being rewritten. The caller is responsible for deciding whose messages
these are; this module is responsible for honouring that decision.
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
    user_id: int,
    term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    cursor: Optional[int] = None,
) -> List[SearchHit]:
    """Messages owned by ``user_id`` containing ``term``, newest first.

    Excludes tombstoned conversations and internal-agent memory slices. Those
    predicates are repeated here rather than left to the partial index: the
    index is an optimisation and must never be the security boundary.
    """
    pattern = f"%{escape_like(term)}%"
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
        .where(
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
            Conversation.agent_id.is_(None),
            ConversationMessage.content.ilike(pattern, escape=_LIKE_ESCAPE),
        )
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
