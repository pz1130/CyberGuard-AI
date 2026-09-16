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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 100

_LIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class SearchHit:
    """One conversation, represented by its newest matching message.

    A keyword commonly matches several messages in the same conversation.
    Returning each of them listed the conversation repeatedly and made ``limit``
    mean "messages", which is not what a person searching asks for. ``hits``
    keeps the number they would otherwise have counted by eye.
    """
    conversation_id: int
    conversation_title: Optional[str]
    message_id: int
    seq: int
    role: str
    content: str
    created_at: datetime
    hits: int = 1


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

    # One row per conversation: its newest matching message represents it, and
    # the count says how much else is in there. Grouping here rather than in
    # the client is what makes `limit` mean conversations and keeps paging
    # correct — a representative is a conversation's maximum matching id, so a
    # page boundary cannot re-surface it through an older message.
    grouped = (
        select(
            ConversationMessage.conversation_id.label("cid"),
            func.max(ConversationMessage.id).label("rep"),
            func.count(ConversationMessage.id).label("hits"),
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(*conditions)
        .group_by(ConversationMessage.conversation_id)
    )
    if cursor is not None:
        grouped = grouped.having(func.max(ConversationMessage.id) < cursor)
    grouped = (grouped
               .order_by(func.max(ConversationMessage.id).desc())
               .limit(max(1, min(int(limit), MAX_SEARCH_LIMIT)))
               .subquery())

    stmt = (
        select(
            ConversationMessage.conversation_id,
            Conversation.title,
            ConversationMessage.id,
            ConversationMessage.seq,
            ConversationMessage.role,
            ConversationMessage.content,
            ConversationMessage.created_at,
            grouped.c.hits,
        )
        .join(grouped, grouped.c.rep == ConversationMessage.id)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .order_by(ConversationMessage.id.desc())
    )

    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(
            conversation_id=row[0], conversation_title=row[1], message_id=row[2],
            seq=row[3], role=row[4], content=row[5], created_at=row[6],
            hits=row[7],
        )
        for row in rows
    ]
