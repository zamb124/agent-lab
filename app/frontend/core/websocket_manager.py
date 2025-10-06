"""
Простой WebSocket менеджер для уведомлений
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """Простой менеджер WebSocket соединений"""

    def __init__(self):
        # Активные соединения по session_id
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Подключить WebSocket"""
        await websocket.accept()
        self.connections[session_id] = websocket
        logger.info(f"WebSocket подключен: {session_id}")

    def disconnect(self, session_id: str):
        """Отключить WebSocket"""
        if session_id in self.connections:
            del self.connections[session_id]
            logger.info(f"WebSocket отключен: {session_id}")

    async def send_to_session(self, session_id: str, message: dict):
        """Отправить сообщение конкретной сессии"""
        if session_id in self.connections:
            try:
                websocket = self.connections[session_id]
                await websocket.send_text(json.dumps(message))
                logger.info(f"Сообщение отправлено в {session_id}: {message['type']}")
            except Exception as e:
                logger.error(f"Ошибка отправки в {session_id}: {e}")
                self.disconnect(session_id)

    async def send_to_all(self, message: dict):
        """Отправить сообщение всем подключенным"""
        disconnected = []

        for session_id, websocket in self.connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Ошибка отправки в {session_id}: {e}")
                disconnected.append(session_id)

        # Убираем отключенные
        for session_id in disconnected:
            self.disconnect(session_id)

        logger.info(
            f"Сообщение отправлено {len(self.connections)} сессиям: {message['type']}"
        )


# Глобальный экземпляр менеджера
websocket_manager = WebSocketManager()


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, session_id: str = None):
    """WebSocket endpoint для уведомлений"""

    # Получаем session_id из cookies если не передан
    if not session_id:
        session_id = websocket.cookies.get("session_id", "anonymous")

    await websocket_manager.connect(websocket, session_id)

    try:
        while True:
            # Ждем сообщения от клиента (ping/pong)
            data = await websocket.receive_text()

            # Простой ping/pong для поддержания соединения
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        websocket_manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket ошибка для {session_id}: {e}")
        websocket_manager.disconnect(session_id)


# Функция для отправки уведомлений (используется в других API)
async def notify_model_updated(model_type: str, model_id: str, session_id: str = None):
    """Уведомить об обновлении модели"""
    message = {
        "type": "MODEL_UPDATED",
        "data": {"model_type": model_type, "model_id": model_id},
    }

    if session_id:
        await websocket_manager.send_to_session(session_id, message)
    else:
        await websocket_manager.send_to_all(message)
