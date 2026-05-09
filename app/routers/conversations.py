"""Chat conversation management router."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.dependencies import get_db, require_permission
from app.core.rbac import Permission
from app.core.auth import AuthenticatedUser
from app.models.conversation import Conversation


class MessageModel(BaseModel):
    role: str
    content: str
    created_at: str | None = None


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    messages_json: str
    created_at: datetime
    updated_at: datetime
    # Per-conversation config overrides
    system_prompt_override: str | None = None
    intent_parser_prompt_override: str | None = None
    summarizer_prompt_override: str | None = None
    model_override: str | None = None
    temperature_override: float | None = None
    knowledge_base_id: int | None = None

    class Config:
        from_attributes = True


class ConversationCreate(BaseModel):
    title: str | None = None
    # Per-conversation config overrides
    system_prompt_override: str | None = None
    intent_parser_prompt_override: str | None = None
    summarizer_prompt_override: str | None = None
    model_override: str | None = None
    temperature_override: float | None = None
    knowledge_base_id: int | None = None


class ConversationUpdate(BaseModel):
    title: str | None = None
    messages_json: str | None = None  # JSON string of messages
    # Per-conversation config overrides
    system_prompt_override: str | None = None
    intent_parser_prompt_override: str | None = None
    summarizer_prompt_override: str | None = None
    model_override: str | None = None
    temperature_override: float | None = None
    knowledge_base_id: int | None = None


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
        title=body.title or "新对话",
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

    if body.title is not None:
        conv.title = body.title
    if body.messages_json is not None:
        conv.messages_json = body.messages_json
    if body.system_prompt_override is not None:
        conv.system_prompt_override = body.system_prompt_override
    if body.intent_parser_prompt_override is not None:
        conv.intent_parser_prompt_override = body.intent_parser_prompt_override
    if body.summarizer_prompt_override is not None:
        conv.summarizer_prompt_override = body.summarizer_prompt_override
    if body.model_override is not None:
        conv.model_override = body.model_override
    if body.temperature_override is not None:
        conv.temperature_override = body.temperature_override
    if body.knowledge_base_id is not None:
        conv.knowledge_base_id = body.knowledge_base_id

    conv.updated_at = datetime.utcnow()
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
    """Append a message to a conversation."""
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

    messages.append({
        "role": body.role,
        "content": body.content,
        "created_at": datetime.utcnow().isoformat(),
    })

    conv.messages_json = json.dumps(messages, ensure_ascii=False)
    conv.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(conv)

    return {"status": "ok", "message_count": len(messages)}