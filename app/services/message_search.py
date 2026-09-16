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
# How many matching messages one conversation contributes. Collapsing without
# this showed a single line for a conversation with several hits, which reads
# as an incomplete result; the cap stops one busy conversation flooding a page.
MAX_MATCHES_PER_CONVERSATION = 3

_LIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class MatchedMessage:
    message_id: int
    seq: int
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class SearchHit:
    """One conversation and the messages in it that matched.

    A keyword commonly matches several messages in the same conversation.
    Returning each of them separately listed the conversation repeatedly and
    made ``limit`` mean "messages", which is not what a person searching asks
    for. ``hits`` is the total; ``matches`` carries the newest
    ``MAX_MATCHES_PER_CONVERSATION`` of them.
    """
    conversation_id: int
    conversation_title: Optional[str]
    hits: int
    matches: List[MatchedMessage]


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

    # One row per conversation, ordered by its newest match. Grouping here
    # rather than in the client is what makes `limit` and paging both mean
    # conversations — a conversation's key is its maximum matching id, so a
    # page boundary cannot re-surface it through an older message.
    grouped = (
        select(
            ConversationMessage.conversation_id.label("cid"),
            func.max(ConversationMessage.id).label("newest"),
            func.count(ConversationMessage.id).label("hits"),
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(*conditions)
        .group_by(ConversationMessage.conversation_id)
    )
    if cursor is not None:
        grouped = grouped.having(func.max(ConversationMessage.id) < cursor)
    rows = (await session.execute(
        grouped.order_by(func.max(ConversationMessage.id).desc())
               .limit(max(1, min(int(limit), MAX_SEARCH_LIMIT)))
    )).all()
    if not rows:
        return []

    order = [r[0] for r in rows]
    totals = {r[0]: r[2] for r in rows}

    # The matching messages of just those conversations, capped per conversation
    # in SQL so one busy conversation cannot drag the whole page.
    ranked = (
        select(
            ConversationMessage.conversation_id.label("cid"),
            ConversationMessage.id.label("mid"),
            ConversationMessage.seq.label("seq"),
            ConversationMessage.role.label("role"),
            ConversationMessage.content.label("content"),
            ConversationMessage.created_at.label("created_at"),
            Conversation.title.label("title"),
            func.row_number().over(
                partition_by=ConversationMessage.conversation_id,
                order_by=ConversationMessage.id.desc(),
            ).label("rank"),
        )
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(*conditions, ConversationMessage.conversation_id.in_(order))
        .subquery()
    )
    matched = (await session.execute(
        select(ranked)
        .where(ranked.c.rank <= MAX_MATCHES_PER_CONVERSATION)
        .order_by(ranked.c.cid, ranked.c.mid.desc())
    )).all()

    by_conversation: dict[int, SearchHit] = {}
    titles: dict[int, Optional[str]] = {}
    grouped_matches: dict[int, List[MatchedMessage]] = {}
    for row in matched:
        titles[row.cid] = row.title
        grouped_matches.setdefault(row.cid, []).append(MatchedMessage(
            message_id=row.mid, seq=row.seq, role=row.role,
            content=row.content, created_at=row.created_at))

    for cid in order:
        by_conversation[cid] = SearchHit(
            conversation_id=cid, conversation_title=titles.get(cid),
            hits=totals[cid], matches=grouped_matches.get(cid, []))
    return [by_conversation[cid] for cid in order]
