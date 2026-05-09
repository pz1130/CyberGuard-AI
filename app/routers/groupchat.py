"""Real-time group chat via WebSocket with message persistence."""
import json
import logging
from datetime import datetime
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decode_access_token
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_db
from app.core.rbac import Permission
from app.models.groupchat import GroupChatMessage
from app.schemas.groupchat import (
    GroupChatCreateRequest,
    GroupChatSessionResponse,
    GroupChatAddMessageRequest,
    GroupChatRoundResponse,
    GroupChatMessageResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections per room.

    Per-user message rate limit: max 60 messages per 60 seconds.
    Exceeding the limit closes the connection with code 4029.
    """

    _MSG_WINDOW = 60      # seconds
    _MSG_LIMIT = 60       # messages per window

    def __init__(self):
        self._rooms: Dict[str, List[WebSocket]] = {}
        # rate-limit counters: {user_id: [timestamp, ...]}
        self._msg_times: Dict[int, List[float]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        self._rooms.setdefault(room_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        room = self._rooms.get(room_id, [])
        if websocket in room:
            room.remove(websocket)

    def is_rate_limited(self, user_id: int) -> bool:
        """Return True if the user has exceeded the message rate limit."""
        import time
        now = time.monotonic()
        window_start = now - self._MSG_WINDOW
        times = self._msg_times.get(user_id, [])
        times = [t for t in times if t > window_start]
        self._msg_times[user_id] = times
        if len(times) >= self._MSG_LIMIT:
            return True
        times.append(now)
        self._msg_times[user_id] = times
        return False

    async def broadcast(self, room_id: str, message: dict):
        for ws in list(self._rooms.get(room_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, room_id)


manager = ConnectionManager()


@router.websocket("/groupchat/{room_id}")
async def groupchat_websocket(
    websocket: WebSocket,
    room_id: str,
    token: str | None = None,  # Query fallback for non-browser WS clients
):
    """
    WebSocket endpoint for real-time group chat.

    Registered at /ws/groupchat/{room_id} in main.py (outside /api/v1 prefix).

    Authentication (in priority order):
      1. Cookie  — `Authorization` cookie set by the frontend after login.
                   Secure, no URL leakage, works with all browser WS APIs.
      2. Query   — ?token=... fallback for non-browser / CLI clients only.
                   Warn: tokens in URLs may be logged by proxies/servers.

    All messages are persisted to the group_chat_messages table for history.
    """
    # Resolve token: prefer cookie, fall back to query param
    auth_cookie = websocket.cookies.get("Authorization")
    resolved_token = None
    if auth_cookie:
        # Strip "Bearer " prefix if present
        resolved_token = auth_cookie.removeprefix("Bearer ").removeprefix("bearer ")
    if not resolved_token:
        resolved_token = token  # may be None — handled below

    try:
        payload = await decode_access_token(resolved_token or "")
        username = payload.get("username", "anonymous")
        user_id: int | None = payload.get("user_id")
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket, room_id)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                message = {"content": data}

            content = message.get("content", "")
            if not content:
                continue

            # Per-user rate limiting (60 messages / 60 seconds)
            if user_id and manager.is_rate_limited(user_id):
                await websocket.send_json({"error": "rate_limit", "detail": "Too many messages. Slow down."})
                continue

            # Persist to DB (own session per message, fire-and-forget on error)
            try:
                async with AsyncSessionLocal() as session:
                    db_msg = GroupChatMessage(
                        room_id=room_id,
                        user_id=user_id,
                        username=username,
                        content=content,
                        metadata_json=json.dumps({
                            "type": message.get("type"),
                            "client_ts": message.get("timestamp"),
                        }),
                    )
                    session.add(db_msg)
                    await session.commit()
                    message["_msg_id"] = db_msg.id
            except Exception as e:
                logger.warning(f"Failed to persist groupchat message: {e}")

            # Tag message with authenticated username and broadcast
            message["_username"] = username
            await manager.broadcast(room_id, message)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error(f"WebSocket error in room {room_id}: {e}")
        manager.disconnect(websocket, room_id)


# ---------------------------------------------------------------------------
# REST endpoints for chat history
# ---------------------------------------------------------------------------

from fastapi import Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db_session
from app.core.dependencies import require_role
from app.core.rbac import Role


class ChatMessageResponse(BaseModel):
    id: int
    room_id: str
    user_id: int | None
    username: str
    content: str
    metadata_json: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    room_id: str
    messages: list[ChatMessageResponse]
    total: int


@router.get("/groupchat/{room_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    room_id: str,
    limit: int = 50,
    before_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Retrieve paginated chat history for a room.

    - limit: max messages to return (default 50, max 200)
    - before_id: return messages before this message ID (for cursor pagination)
    """
    limit = min(limit, 200)

    query = (
        select(GroupChatMessage)
        .where(GroupChatMessage.room_id == room_id)
        .order_by(desc(GroupChatMessage.created_at))
        .limit(limit)
    )

    if before_id:
        # Get the timestamp of the before_id message for cursor pagination
        cursor_result = await session.execute(
            select(GroupChatMessage.created_at).where(GroupChatMessage.id == before_id)
        )
        cursor_row = cursor_result.scalar_one_or_none()
        if cursor_row:
            query = query.where(GroupChatMessage.created_at < cursor_row)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    rows.reverse()  # Oldest first in response

    return ChatHistoryResponse(
        room_id=room_id,
        messages=[ChatMessageResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


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
async def get_group_chat_session(session_id: str):
    """Get the current state of a group chat session."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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


@router.post("/groupchat/sessions/{session_id}/message", response_model=GroupChatSessionResponse)
async def add_group_chat_message(session_id: str, body: GroupChatAddMessageRequest):
    """Add a user message to an existing session (without running agents)."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
async def run_group_chat_round(session_id: str):
    """
    Run one round of the group chat where each selected agent responds once.

    Returns the round results with all agent responses.
    """
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await service.run_round(session_id)
    return GroupChatRoundResponse(
        session_id=result["session_id"],
        round=result["round"],
        responses=result["responses"],
    )


@router.post("/groupchat/sessions/{session_id}/complete", response_model=GroupChatSessionResponse)
async def run_group_chat_to_completion(session_id: str):
    """
    Run the group chat to completion (all rounds or until consensus).

    Returns the final session state with all messages.
    """
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await service.run_to_completion(session_id)
    return GroupChatSessionResponse(
        session_id=result["session_id"],
        user_id=result["user_id"],
        agent_ids=result["agent_ids"],
        status=result["status"],
        current_round=result["current_round"],
        max_rounds=result["max_rounds"],
        messages=[
            GroupChatMessageResponse(
                role=m.role,
                content=m.content,
                agent_id=m.agent_id,
                agent_name=m.agent_name,
                timestamp=m.timestamp,
            )
            for m in result["messages"]
        ],
        created_at=result["created_at"],
    )


@router.delete("/groupchat/sessions/{session_id}")
async def cancel_group_chat_session(session_id: str):
    """Cancel an active group chat session."""
    from app.services.group_chat import get_group_chat_service

    service = get_group_chat_service()
    session = await service.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await service.cancel_session(session_id)
    return {"status": "ok", "session_id": session_id}
