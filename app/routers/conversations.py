"""Chat conversation management router."""
from typing import Optional
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.core.time import utc_now
from app.models.conversation import Conversation


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
    messages_json: str
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
    messages_json: Optional[str] = None  # JSON string of messages
    # Per-conversation config overrides
    system_prompt_override: Optional[str] = None
    intent_parser_prompt_override: Optional[str] = None
    summarizer_prompt_override: Optional[str] = None
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    knowledge_base_id: Optional[int] = None


_REQUIRED_UPDATE_FIELDS = {"title", "messages_json"}


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
    """List all conversations for current user."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.user_id)
        .order_by(desc(Conversation.updated_at))
        .limit(50)
    )
    return [ConversationResponse.model_validate(c) for c in result.scalars().all()]


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
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()


@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_permission(Permission.TASK_EXECUTE)
    ),
):
    """Get messages for a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.user_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        messages = json.loads(conv.messages_json or "[]")
    except json.JSONDecodeError:
        messages = []
    return {"messages": messages}


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
