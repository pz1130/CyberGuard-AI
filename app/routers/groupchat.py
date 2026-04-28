"""Real-time group chat via WebSocket."""
import json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.dependencies import get_db
from app.core.auth import verify_token
from app.services.group_chat import GroupChatService

router = APIRouter()
logger = logging.getLogger(__name__)
room_manager = GroupChatService()


@router.websocket("/chat/ws/{room_id}")
async def groupchat_websocket(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for real-time group chat.

    Args:
        websocket: WebSocket connection
        room_id: Chat room identifier
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    if token:
        try:
            verify_token(token)
        except Exception:
            await websocket.close(code=4001)
            return

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            await room_manager.broadcast(room_id, message_data)
    except WebSocketDisconnect:
        room_manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=4000)
