"""Multi-agent group chat REST API.

This module used to also expose a WebSocket-based human-to-human room chat at
`/ws/groupchat/{room_id}`; that feature was removed in migration 005 since
single-operator deployments had no use for it. All remaining endpoints are
multi-agent session APIs mounted under `/api/v1`.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_role
from app.core.rbac import Role
from app.schemas.groupchat import (
    GroupChatCreateRequest,
    GroupChatSessionResponse,
    GroupChatAddMessageRequest,
    GroupChatRoundResponse,
    GroupChatMessageResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


async def _load_owned_session(service, session_id: str, current_user):
    """Load a session the caller is entitled to see, else 404.

    Every endpoint below drives real agent execution or exposes the full
    transcript, so authentication alone is not enough — a session belongs to the
    user who created it. Non-owners get 404 rather than 403 so the API does not
    confirm that a session id exists.
    """
    session = await service.load_session(session_id)
    if not session or session.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# --- Multi-Agent Group Chat Service Endpoints ---

@router.post("/groupchat/sessions", response_model=GroupChatSessionResponse)
async def create_group_chat_session(
    body: GroupChatCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(Role.ADMIN)),
):
    """
    Create a new multi-agent group chat session.

    Selects agents and sends an initial message to kick off the discussion.
    """
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()

    session_id = await service.create_session(
        user_id=current_user.user_id,
        agent_ids=body.agent_ids,
        initial_message=body.initial_message,
        max_rounds=body.max_rounds,
    )

    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return GroupChatSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        agent_ids=session.agent_ids,
        status=session.status,
        current_round=session.current_round,
        max_rounds=session.max_rounds,
        messages=[
            GroupChatMessageResponse(
                role=m.role,
                content=m.content,
                agent_id=m.agent_id,
                agent_name=m.agent_name,
                timestamp=m.timestamp,
            )
            for m in session.messages
        ],
        created_at=session.created_at,
    )


@router.get("/groupchat/sessions/{session_id}", response_model=GroupChatSessionResponse)
async def get_group_chat_session(
    session_id: str,
    current_user=Depends(require_role(Role.ADMIN)),
):
    """Get the current state of a group chat session."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await _load_owned_session(service, session_id, current_user)

    return GroupChatSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        agent_ids=session.agent_ids,
        status=session.status,
        current_round=session.current_round,
        max_rounds=session.max_rounds,
        messages=[
            GroupChatMessageResponse(
                role=m.role,
                content=m.content,
                agent_id=m.agent_id,
                agent_name=m.agent_name,
                timestamp=m.timestamp,
            )
            for m in session.messages
        ],
        created_at=session.created_at,
        running=await service.is_running(session_id),
    )


@router.post("/groupchat/sessions/{session_id}/message", response_model=GroupChatSessionResponse)
async def add_group_chat_message(
    session_id: str,
    body: GroupChatAddMessageRequest,
    current_user=Depends(require_role(Role.ADMIN)),
):
    """Add a user message to an existing session (without running agents)."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    await _load_owned_session(service, session_id, current_user)

    await service.add_message(
        session_id=session_id,
        content=body.content,
        role=body.role,
        agent_id=body.agent_id,
    )

    session = await service.load_session(session_id)
    return GroupChatSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        agent_ids=session.agent_ids,
        status=session.status,
        current_round=session.current_round,
        max_rounds=session.max_rounds,
        messages=[
            GroupChatMessageResponse(
                role=m.role,
                content=m.content,
                agent_id=m.agent_id,
                agent_name=m.agent_name,
                timestamp=m.timestamp,
            )
            for m in session.messages
        ],
        created_at=session.created_at,
    )


@router.post("/groupchat/sessions/{session_id}/round", response_model=GroupChatRoundResponse)
async def run_group_chat_round(
    session_id: str,
    current_user=Depends(require_role(Role.ADMIN)),
):
    """
    Run one round of the group chat where each selected agent responds once.

    Returns the round results with all agent responses.
    """
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    await _load_owned_session(service, session_id, current_user)

    result = await service.run_round(session_id)
    return GroupChatRoundResponse(
        session_id=result["session_id"],
        round=result["round"],
        responses=result["responses"],
    )


@router.post("/groupchat/sessions/{session_id}/complete", response_model=GroupChatSessionResponse)
async def run_group_chat_to_completion(
    session_id: str,
    current_user=Depends(require_role(Role.ADMIN)),
):
    """
    Start running the group chat to completion (all rounds or until consensus).

    Dispatches the discussion as a background task and returns immediately with
    ``running=True``; the discussion can take minutes (rounds × agents × LLM
    latency) and must not block the single-worker event loop. Poll
    ``GET /groupchat/sessions/{session_id}`` until ``running`` is false.
    """
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    await _load_owned_session(service, session_id, current_user)

    result = await service.start_completion(session_id)
    return GroupChatSessionResponse(
        session_id=result["session_id"],
        user_id=result["user_id"],
        agent_ids=result["agent_ids"],
        status=result["status"],
        current_round=result["current_round"],
        max_rounds=result["max_rounds"],
        messages=[
            GroupChatMessageResponse(
                role=m["role"],
                content=m["content"],
                agent_id=m.get("agent_id"),
                agent_name=m.get("agent_name"),
                timestamp=m["timestamp"],
            )
            for m in result["messages"]
        ],
        created_at=result["created_at"],
        running=await service.is_running(session_id),
    )


@router.delete("/groupchat/sessions/{session_id}")
async def cancel_group_chat_session(
    session_id: str,
    current_user=Depends(require_role(Role.ADMIN)),
):
    """Cancel an active group chat session."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    await _load_owned_session(service, session_id, current_user)

    await service.cancel_session(session_id)
    return {"status": "ok", "session_id": session_id}
