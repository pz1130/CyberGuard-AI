"""Append-only, hash-chained storage for chat messages.

History used to be ``conversations.messages_json``, one JSON array rewritten on
every append, so message n cost the size of messages 1..n-1. Each message is
now a row in ``conversation_messages``, chained to the previous message in the
same conversation (``app.services.conversation_chain``).

The conversation row is still locked (``SELECT ... FOR UPDATE``) while
appending. That lock no longer exists to protect a read-modify-write of the
blob; it serialises the readers of the chain head, so two workers cannot
compute the same ``seq``. ``uq_conv_messages_seq`` is the backstop if it ever
fails to.

``parse_messages`` / ``serialize_messages`` / ``stamp_message`` are kept: the
legacy column still has to be readable, and the backfill relies on the same
parsing being forgiving.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.services.conversation_chain import GENESIS, entry_hash


def parse_messages(raw: Optional[str]) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [m for m in data if isinstance(m, dict)]


def serialize_messages(messages: Sequence[Dict[str, Any]]) -> str:
    return json.dumps(list(messages), ensure_ascii=False)


def stamp_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(msg)
    if "created_at" not in out:
        out["created_at"] = datetime.now(timezone.utc).isoformat()
    return out


DEFAULT_PAGE_LIMIT = 200
MAX_PAGE_LIMIT = 1000

# Roles a chat model can be replayed with. Other roles are stored — the
# transcript records everything that happened — but not sent back to a model.
_LLM_ROLES = ("user", "assistant")


def _coerce_created_at(value: Any) -> datetime:
    """Normalise to the naive-UTC datetime this codebase stores.

    The chain hashes the value returned here, i.e. the value that lands in the
    column, so that a row read back can be re-verified.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return utc_now()
    else:
        return utc_now()
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _build_rows(
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    next_seq: int,
    prev_hash: str,
) -> List[ConversationMessage]:
    rows: List[ConversationMessage] = []
    seq = next_seq
    for message in new_messages:
        role = str(message.get("role") or "")[:32]
        content = message.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        created_at = _coerce_created_at(message.get("created_at"))
        run_id = message.get("run_id")
        turn_id = message.get("turn_id")
        digest = entry_hash(
            conversation_id=conv_id, seq=seq, role=role, content=content,
            created_at=created_at, run_id=run_id, turn_id=turn_id,
            prev_hash=prev_hash,
        )
        rows.append(ConversationMessage(
            conversation_id=conv_id, seq=seq, role=role, content=content,
            run_id=run_id, turn_id=turn_id, created_at=created_at,
            backfilled=False, prev_hash=prev_hash, entry_hash=digest,
        ))
        prev_hash = digest
        seq += 1
    return rows


def _head_statement(conv_id: int):
    return (
        select(ConversationMessage.seq, ConversationMessage.entry_hash)
        .where(ConversationMessage.conversation_id == conv_id)
        .order_by(ConversationMessage.seq.desc())
        .limit(1)
    )


def _conversation_statement(conv_id: int, user_id: Optional[int], lock: bool):
    stmt = select(Conversation).where(Conversation.id == conv_id)
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    return stmt.with_for_update() if lock else stmt


async def append_messages_locked(
    session: AsyncSession,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Append messages under row lock. Returns (conv, total_count) or (None, 0)."""
    conv = (await session.execute(
        _conversation_statement(conv_id, user_id, bool(new_messages))
    )).scalar_one_or_none()
    if not conv:
        return None, 0

    head = (await session.execute(_head_statement(conv_id))).first()
    next_seq = 0 if head is None else head[0] + 1
    prev_hash = GENESIS if head is None else head[1]

    if not new_messages:
        return conv, next_seq

    rows = _build_rows(conv_id, new_messages, next_seq, prev_hash)
    session.add_all(rows)
    # The session is built with autoflush=False, so without this a second
    # append before the commit would not see these rows when it reads the chain
    # head, and both would compute the same seq. uq_conv_messages_seq catches
    # that, but batching two appends is an ordinary thing for a caller to do.
    await session.flush()
    conv.updated_at = utc_now()
    return conv, next_seq + len(rows)


def append_messages_locked_sync(
    session: Session,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Sync variant for Celery workers."""
    conv = session.execute(
        _conversation_statement(conv_id, user_id, bool(new_messages))
    ).scalar_one_or_none()
    if not conv:
        return None, 0

    head = session.execute(_head_statement(conv_id)).first()
    next_seq = 0 if head is None else head[0] + 1
    prev_hash = GENESIS if head is None else head[1]

    if not new_messages:
        return conv, next_seq

    rows = _build_rows(conv_id, new_messages, next_seq, prev_hash)
    session.add_all(rows)
    session.flush()   # see the async twin: autoflush is off
    conv.updated_at = utc_now()
    return conv, next_seq + len(rows)


# -------- reads --------

def _page_statement(conv_id: int, limit: int, before_seq: Optional[int]):
    stmt = select(ConversationMessage).where(
        ConversationMessage.conversation_id == conv_id)
    if before_seq is not None:
        stmt = stmt.where(ConversationMessage.seq < before_seq)
    return stmt.order_by(ConversationMessage.seq.desc()).limit(
        max(1, min(int(limit), MAX_PAGE_LIMIT)))


async def fetch_messages(
    session: AsyncSession,
    conv_id: int,
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
    before_seq: Optional[int] = None,
) -> List[ConversationMessage]:
    """The newest ``limit`` messages before ``before_seq``, in reading order."""
    rows = (await session.execute(
        _page_statement(conv_id, limit, before_seq))).scalars().all()
    return list(reversed(rows))


async def fetch_recent(
    session: AsyncSession, conv_id: int, limit: int
) -> List[ConversationMessage]:
    return await fetch_messages(session, conv_id, limit=limit)


def fetch_recent_sync(
    session: Session, conv_id: int, limit: int
) -> List[ConversationMessage]:
    rows = session.execute(_page_statement(conv_id, limit, None)).scalars().all()
    return list(reversed(rows))


def to_message_dict(row: ConversationMessage) -> Dict[str, Any]:
    """The shape the chat client has always received."""
    return {
        "role": row.role,
        "content": row.content,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def to_llm_turns(rows: Sequence[ConversationMessage]) -> List[Dict[str, str]]:
    """Replayable turns only — the filter the callers used to apply inline."""
    return [
        {"role": row.role, "content": row.content}
        for row in rows
        if row.role in _LLM_ROLES and row.content
    ]
