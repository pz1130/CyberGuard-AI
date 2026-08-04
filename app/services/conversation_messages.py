"""Atomic conversation message append (multi-worker safe).

``conversations.messages_json`` is a single TEXT blob. Naïve read-modify-write
under ``API_WORKERS>1`` loses concurrent appends. All append paths must lock
the row (``SELECT … FOR UPDATE``) before rewriting the JSON array.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.conversation import Conversation


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


async def append_messages_locked(
    session: AsyncSession,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Append messages under row lock. Returns (conv, total_count) or (None, 0)."""
    if not new_messages:
        stmt = select(Conversation).where(Conversation.id == conv_id)
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        if not conv:
            return None, 0
        return conv, len(parse_messages(conv.messages_json))

    stmt = (
        select(Conversation)
        .where(Conversation.id == conv_id)
        .with_for_update()
    )
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        return None, 0

    messages = parse_messages(conv.messages_json)
    for m in new_messages:
        messages.append(stamp_message(m))
    conv.messages_json = serialize_messages(messages)
    conv.updated_at = datetime.now(timezone.utc)
    return conv, len(messages)


def append_messages_locked_sync(
    session: Session,
    conv_id: int,
    new_messages: Sequence[Dict[str, Any]],
    *,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Conversation], int]:
    """Sync variant for Celery workers."""
    if not new_messages:
        stmt = select(Conversation).where(Conversation.id == conv_id)
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        conv = session.execute(stmt).scalar_one_or_none()
        if not conv:
            return None, 0
        return conv, len(parse_messages(conv.messages_json))

    stmt = (
        select(Conversation)
        .where(Conversation.id == conv_id)
        .with_for_update()
    )
    if user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    conv = session.execute(stmt).scalar_one_or_none()
    if not conv:
        return None, 0

    messages = parse_messages(conv.messages_json)
    for m in new_messages:
        messages.append(stamp_message(m))
    conv.messages_json = serialize_messages(messages)
    conv.updated_at = datetime.now(timezone.utc)
    return conv, len(messages)
