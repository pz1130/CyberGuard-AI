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
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_db, rate_limit, require_permission
from app.services.conversation_messages import (
    append_messages_locked,
    fetch_recent,
    to_llm_turns,
)
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

    # The global kill switch is an execution boundary, not just a sub-agent
    # control. Check it before loading history or constructing an LLM stream so
    # an emergency stop cannot still produce direct MASTER/AUTO output.
    from app.services.kill_switch import is_halted
    if await is_halted():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Global kill switch is active; chat operations are suspended",
        )

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
            from app.models.conversation import Conversation
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Conversation).where(
                        Conversation.id == body.conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                conversation = result.scalar_one_or_none()
                if conversation:
                    rows = await fetch_recent(session, body.conversation_id, 20)
                    conversation_history = to_llm_turns(rows)
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
    try:
        async with AsyncSessionLocal() as session:
            # Goes through the chained append, which takes the row lock and
            # does the ownership check itself. The code this replaced did an
            # unlocked read-modify-write of the blob, silently losing a
            # concurrent append under API_WORKERS>1.
            conv, _ = await append_messages_locked(
                session,
                conversation_id,
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_response},
                ],
                user_id=user_id,
            )
            if not conv:
                return

            # Auto-title while the conversation has none. Keying off absence
            # rather than a magic string means the sentinel cannot drift away
            # from the placeholder and silently stop this from ever running.
            if not conv.title and user_message:
                try:
                    from app.services.llm_router import get_llm_router
                    llm = get_llm_router()
                    title = await llm.chat(
                        messages=[{
                            "role": "user",
                            "content": (
                                "Write a short title for this conversation, at most "
                                "six words, in the same language as the message, with "
                                f"no surrounding quotes:\n{user_message[:200]}"
                            ),
                        }],
                        temperature_override=0.3,
                    )
                    conv.title = title.strip().strip('"').strip("'")[:50] or None
                except Exception:
                    pass  # Title stays as default if LLM fails

            await session.commit()
    except Exception as e:
        logger.warning(f"[stream_chat] Failed to persist conversation {conversation_id}: {e}")
