"""Real-time group chat via WebSocket."""
import json
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections per room."""

    def __init__(self):
        self._rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        self._rooms.setdefault(room_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        room = self._rooms.get(room_id, [])
        if websocket in room:
            room.remove(websocket)

    async def broadcast(self, room_id: str, message: dict):
        for ws in list(self._rooms.get(room_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, room_id)


manager = ConnectionManager()


@router.websocket("/groupchat/{room_id}")
async def groupchat_websocket(websocket: WebSocket, room_id: str):
    """
    WebSocket endpoint for real-time group chat.
    Registered at /ws/groupchat/{room_id} in main.py (outside /api/v1 prefix).
    """
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                message = {"content": data}
            await manager.broadcast(room_id, message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
    except Exception as e:
        logger.error(f"WebSocket error in room {room_id}: {e}")
        manager.disconnect(websocket, room_id)
