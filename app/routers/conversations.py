"""Chat conversation management router."""
from typing import Optional
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.time import utc_now
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.services.conversation_messages import (
    DEFAULT_PAGE_LIMIT,
    fetch_messages,
    to_message_dict,
)


class MessageModel(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    # Absent until the user renames it or auto-titling fills it in; the client
    # renders its own translated placeholder rather than reading a stored one.
    title: Optional[str] = None
    # The transcript is no longer shipped with the list: it made every listing
    # carry every message of 50 conversations. Read it from
    # GET /conversations/{id}/messages, a page at a time.
    message_count: int = 0
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Per-conversation config overrides
    system_prompt_override: Optional[str] = None
    intent_parser_prompt_override: Optional[str] = None
    summarizer_prompt_override: Optional[str] = None
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    knowledge_base_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    # Per-conversation config overrides
    system_prompt_override: Optional[str] = None
    intent_parser_prompt_override: Optional[str] = None
    summarizer_prompt_override: Optional[str] = None
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    knowledge_base_id: Optional[int] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    # Per-conversation config overrides
    system_prompt_override: Optional[str] = None
    intent_parser_prompt_override: Optional[str] = None
    summarizer_prompt_override: Optional[str] = None
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    knowledge_base_id: Optional[int] = None


_REQUIRED_UPDATE_FIELDS = {"title"}


def apply_conversation_update(conv, body: ConversationUpdate) -> None:
    """Apply fields the client actually sent, including explicit JSON null.

    `is not None` skips clearing: the session UI sends null to drop a knowledge
    base or custom prompt, and that write must land.
    """
    data = body.model_dump(exclude_unset=True)
    for key in _REQUIRED_UPDATE_FIELDS:
        if data.get(key) is None:
            data.pop(key, None)
    for key, value in data.items():
        setattr(conv, key, value)


class AppendMessageRequest(BaseModel):
    role: str  # "user" or "assistant"
    content: str


router = APIRouter()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """List the caller's live conversations, newest first."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(desc(Conversation.updated_at))
        .limit(50)
    )
    conversations = list(result.scalars().all())
    if not conversations:
        return []

    ids = [c.id for c in conversations]

    counts = dict((await db.execute(
        select(ConversationMessage.conversation_id, func.count(ConversationMessage.id))
        .where(ConversationMessage.conversation_id.in_(ids))
        .group_by(ConversationMessage.conversation_id)
    )).all())

    # DISTINCT ON is PostgreSQL-only, which this deployment is. It gets the
    # newest message per conversation in one pass instead of one query each.
    previews = dict((await db.execute(
        select(ConversationMessage.conversation_id, ConversationMessage.content)
        .where(ConversationMessage.conversation_id.in_(ids))
        .distinct(ConversationMessage.conversation_id)
        .order_by(ConversationMessage.conversation_id, ConversationMessage.seq.desc())
    )).all())

    responses = []
    for conv in conversations:
        payload = ConversationResponse.model_validate(conv)
        payload.message_count = counts.get(conv.id, 0)
        preview = previews.get(conv.id)
        payload.last_message_preview = preview[:200] if preview else None
        responses.append(payload)
    return responses


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Create a new conversation."""
    conv = Conversation(
        user_id=current_user.user_id,
        title=(body.title or None),
        messages_json="[]",
        system_prompt_override=body.system_prompt_override,
        intent_parser_prompt_override=body.intent_parser_prompt_override,
        summarizer_prompt_override=body.summarizer_prompt_override,
        model_override=body.model_override,
        temperature_override=body.temperature_override,
        knowledge_base_id=body.knowledge_base_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Get a conversation by ID."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conv)


@router.put("/conversations/{conv_id}", response_model=ConversationResponse)
async def update_conversation(
    conv_id: int,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Update a conversation (rename or append messages)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    apply_conversation_update(conv, body)

    # The schema stores TIMESTAMP WITHOUT TIME ZONE. Keep the value in UTC,
    # but strip tzinfo so asyncpg does not reject the update.
    conv.updated_at = utc_now()
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Delete a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Immutability-first: a user removing a conversation from their sidebar
    # must not be able to destroy the record of what the assistant told them.
    # Retention (Round 3) decides when the rows actually go.
    conv.deleted_at = utc_now()
    await db.commit()


@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
    limit: int = DEFAULT_PAGE_LIMIT,
    before_seq: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Get messages for a conversation, newest-last, most recent page first."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = await fetch_messages(db, conv_id, limit=limit, before_seq=before_seq)
    return {"messages": [to_message_dict(row) for row in rows]}


@router.post("/conversations/{conv_id}/messages")
async def append_message(
    conv_id: int,
    body: AppendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Append a message to a conversation (row-locked; multi-worker safe)."""
    from app.services.conversation_messages import append_messages_locked

    conv, count = await append_messages_locked(
        db,
        conv_id,
        [{"role": body.role, "content": body.content}],
        user_id=current_user.user_id,
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.commit()
    await db.refresh(conv)

    return {"status": "ok", "message_count": count}
