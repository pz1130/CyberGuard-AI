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
from app.services.message_search import DEFAULT_SEARCH_LIMIT, search_messages
from app.services.message_snippet import snippet


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
    # True once retention has disposed of the messages. The row survives so the
    # person sees an archived conversation rather than an empty one.
    archived: bool = False
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
            # An internal agent's memory is stored as a conversations row owned
            # by the person (internal_agent.py:181). It is not a conversation
            # they had.
            Conversation.agent_id.is_(None),
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
        payload.archived = conv.purged_at is not None
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


# Declared before /conversations/{conv_id}: FastAPI matches in declaration
# order, and "search" would otherwise bind to conv_id and fail int parsing.
@router.get("/conversations/search")
async def search_conversation_messages(
    q: str = "",
    limit: int = DEFAULT_SEARCH_LIMIT,
    cursor: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Search your own chat messages.

    The owner comes from the token and is never accepted as a parameter; a
    user_id here would make this an admin endpoint wearing a self-service name.
    """
    term = (q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="q is required")

    hits = await search_messages(
        db, user_id=current_user.user_id, term=term, limit=limit, cursor=cursor)

    return {
        "results": [
            {
                "conversation_id": hit.conversation_id,
                "conversation_title": hit.conversation_title,
                "hits": hit.hits,
                "matches": [
                    {
                        "message_id": m.message_id,
                        "seq": m.seq,
                        "role": m.role,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                        "snippet": snippet(m.content, term),
                    }
                    for m in hit.matches
                ],
            }
            for hit in hits
        ],
        # The newest match of the last conversation on this page.
        "next_cursor": (hits[-1].matches[0].message_id
                        if hits and hits[-1].matches else None),
    }


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

    if conv.purged_at is not None:
        # A second chain starting at seq 0 would collide with the one already
        # exported, and the history it belongs to no longer lives here. Raised
        # before the commit below, so nothing is written.
        raise HTTPException(
            status_code=409,
            detail="This conversation has been archived and cannot be continued.")

    await db.commit()
    await db.refresh(conv)

    return {"status": "ok", "message_count": count}


@router.post("/conversations/export")
async def export_conversations(
    older_than_days: int = 0,
    retain_days: int = 365,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Mirror conversations to write-once storage.

    older_than_days=0 exports everything; retention disposes of nothing that
    has not been through here first.
    """
    from app.services.conversation_export import export_eligible

    try:
        summary = await export_eligible(
            db, older_than_days=older_than_days, retain_days=retain_days)
    except RuntimeError as exc:
        # Object storage is not configured. An uncaught RuntimeError becomes a
        # bare "Internal server error", leaving the operator guessing at the
        # one thing that blocks retention entirely — purge finding nothing
        # eligible is the downstream symptom of exactly this.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.commit()
    return summary


@router.post("/conversations/purge")
async def purge_conversations(
    older_than_days: int = 365,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Permission.AUDIT_READ)),
):
    """Dispose of archived conversations older than the cutoff.

    Dry runs unless `confirm` is true. This is the one irreversible operation
    in the product; it should not be a typo away.
    """
    from app.services.conversation_purge import purge_eligible

    return await purge_eligible(
        db, older_than_days=older_than_days, confirm=confirm)
