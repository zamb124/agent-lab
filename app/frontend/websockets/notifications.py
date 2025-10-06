"""
WebSocket для уведомлений (из старого api/websocket.py)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket-notifications"])


class ConnectionManager:
    """Менеджер WebSocket соединений для уведомлений"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket подключен: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket отключен: {session_id}")

    async def send_personal_message(self, message: str, session_id: str):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(message)


manager = ConnectionManager()


@router.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для уведомлений"""
    session_id = websocket.query_params.get("session_id", "default")
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Получено от {session_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(session_id)


async def notify_model_updated(model_type: str, model_id: str = None):
    """Отправить уведомление об обновлении модели"""
    message = f"model_updated:{model_type}"
    if model_id:
        message += f":{model_id}"
    
    for session_id, websocket in manager.active_connections.items():
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления {session_id}: {e}")

