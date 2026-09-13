"""SSE streaming chat endpoint.

POST /api/v1/chat/stream

Runs the LLM directly in the FastAPI process (no Celery), streaming
tokens back to the client via Server-Sent Events.

Suitable for direct conversation (no multi-agent routing). When the user
needs sub-agent orchestration, they should use POST /api/v1/chat instead
(async task-based).

SSE format::
    data: {"type": "chunk", "content": "...token..."}\n\n
    data: {"type": "done",  "content": "", "usage": {...}}\n\n
    data: {"type": "error", "content": "..."}\n\n
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.auth import AuthenticatedUser
from app.core.time import utc_now
from app.core.dependencies import get_db, rate_limit, require_permission
from app.core.guardrails import check_prompt_sync
from app.core.rbac import Permission
from app.schemas.chat import ChatRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    current_user: AuthenticatedUser = Depends(
        rate_limit(requests_per_minute=30, requests_per_hour=500, burst_limit=5)(
            require_permission(Permission.TASK_EXECUTE)
        )
    ),
):
    """Stream LLM response tokens via Server-Sent Events.

    The client receives chunks as they arrive from the provider:
    - ``data: {"type":"chunk","content":"..."}``
    - ``data: {"type":"done","content":""}``
    - ``data: {"type":"error","content":"..."}``

    Connect with EventSource (browser) or ``curl -N``.
    """
    user_id = current_user.user_id

    # Guardrail check (sync, no LLM classifier in hot path)
    gr = check_prompt_sync(body.message)
    if gr.blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input blocked: {gr.message} (risk={gr.risk_level})",
        )

    # Load conversation history if conversation_id provided
    conversation_history: list[dict] = []
    conversation = None
    if body.conversation_id:
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.conversation import Conversation
            from sqlalchemy import select
            import json as _json
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Conversation).where(
                        Conversation.id == body.conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                conversation = result.scalar_one_or_none()
            if conversation:
                try:
                    msgs = _json.loads(conversation.messages_json or "[]")
                    conversation_history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in msgs[-20:]
                        if m.get("role") in ("user", "assistant") and m.get("content")
                    ]
                except Exception:
                    conversation_history = []
        except Exception as e:
            logger.warning(f"[stream_chat] Failed to load conversation: {e}")

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.services.llm_router import get_llm_router
        from app.core.langfuse_tracing import trace_run
        router_llm = get_llm_router()
        session_id = str(body.conversation_id) if body.conversation_id else f"chat:{user_id}"

        # Build messages: system prompt override + history + current message
        messages: list[dict] = []
        system_prompt = getattr(conversation, "system_prompt_override", None) if conversation else None
        temp_override = getattr(conversation, "temperature_override", None) if conversation else None

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": body.message})

        accumulated: list[str] = []
        error_occurred = False

        try:
            with trace_run(session_id=session_id, agent_name="chat", user_id=user_id):
                async for chunk in router_llm.stream_chat(
                    messages=messages,
                    provider_id=body.provider_id,
                    model=body.model,
                    temperature_override=temp_override,
                ):
                    accumulated.append(chunk)
                    payload = json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"

        except Exception as e:
            error_occurred = True
            logger.error(f"[stream_chat] LLM error for user {user_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        # Signal completion
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

        if error_occurred or not accumulated:
            return

        # Persist to conversation history (fire-and-forget)
        full_response = "".join(accumulated)
        if body.conversation_id and conversation is not None:
            asyncio.create_task(
                _persist_to_conversation(
                    conversation_id=body.conversation_id,
                    user_id=user_id,
                    user_message=body.message,
                    assistant_response=full_response,
                )
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _persist_to_conversation(
    conversation_id: int,
    user_id: int,
    user_message: str,
    assistant_response: str,
) -> None:
    """Save the streamed exchange to the conversations table."""
    import json as _json
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.conversation import Conversation
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            conv = result.scalar_one_or_none()
            if not conv:
                return

            messages = _json.loads(conv.messages_json or "[]")
            now = datetime.now(timezone.utc).isoformat()
            messages.append({"role": "user", "content": user_message, "created_at": now})
            messages.append({"role": "assistant", "content": assistant_response, "created_at": now})
            conv.messages_json = _json.dumps(messages, ensure_ascii=False)
            conv.updated_at = utc_now()

            # Auto-title if still default
            if conv.title == "新对话" and user_message:
                try:
                    from app.services.llm_router import get_llm_router
                    llm = get_llm_router()
                    title = await llm.chat(
                        messages=[{
                            "role": "user",
                            "content": f"请为以下对话生成一个简洁标题（10字以内，不加引号）：\n{user_message[:200]}",
                        }],
                        temperature_override=0.3,
                    )
                    conv.title = title.strip().strip('"').strip("'")[:50] or "新对话"
                except Exception:
                    pass  # Title stays as default if LLM fails

            await session.commit()
    except Exception as e:
        logger.warning(f"[stream_chat] Failed to persist conversation {conversation_id}: {e}")
