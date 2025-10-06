"""
Универсальный WebSocket менеджер для всех типов соединений
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Optional, Literal
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

ConnectionType = Literal["chat", "notifications", "updates"]


class WebSocketManager:
    """Универсальный менеджер WebSocket соединений"""

    def __init__(self):
        # Соединения сгруппированы по типу: {type: {session_id: websocket}}
        self.connections: Dict[ConnectionType, Dict[str, WebSocket]] = {
            "chat": {},
            "notifications": {},
            "updates": {}
        }
        # Polling задачи для типов соединений
        self.polling_tasks: Dict[str, asyncio.Task] = {}

    async def connect(
        self, 
        websocket: WebSocket, 
        session_id: str, 
        connection_type: ConnectionType = "notifications"
    ):
        """Подключить WebSocket"""
        await websocket.accept()
        self.connections[connection_type][session_id] = websocket
        logger.info(f"WebSocket подключен: {connection_type}:{session_id}")

    def disconnect(
        self, 
        session_id: str, 
        connection_type: ConnectionType = "notifications"
    ):
        """Отключить WebSocket"""
        if session_id in self.connections[connection_type]:
            del self.connections[connection_type][session_id]
            logger.info(f"WebSocket отключен: {connection_type}:{session_id}")
        
        # Остановить polling задачу если есть
        polling_key = f"{connection_type}:{session_id}"
        if polling_key in self.polling_tasks:
            self.polling_tasks[polling_key].cancel()
            del self.polling_tasks[polling_key]

    async def send_to_session(
        self, 
        session_id: str, 
        message: dict,
        connection_type: ConnectionType = "notifications"
    ):
        """Отправить сообщение конкретной сессии"""
        if session_id in self.connections[connection_type]:
            try:
                websocket = self.connections[connection_type][session_id]
                await websocket.send_text(json.dumps(message))
                logger.info(f"Сообщение отправлено в {connection_type}:{session_id}: {message.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Ошибка отправки в {connection_type}:{session_id}: {e}")
                self.disconnect(session_id, connection_type)

    async def send_to_all(
        self, 
        message: dict,
        connection_type: ConnectionType = "notifications"
    ):
        """Отправить сообщение всем подключенным в указанном типе"""
        disconnected = []
        
        connections = self.connections[connection_type]
        for session_id, websocket in connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Ошибка отправки в {connection_type}:{session_id}: {e}")
                disconnected.append(session_id)

        # Убираем отключенные
        for session_id in disconnected:
            self.disconnect(session_id, connection_type)

        logger.info(
            f"Сообщение отправлено {len(connections)} сессиям типа {connection_type}: {message.get('type', 'unknown')}"
        )
    
    async def send_to_all_types(self, message: dict):
        """Отправить сообщение всем соединениям всех типов"""
        for connection_type in self.connections.keys():
            await self.send_to_all(message, connection_type)
    
    def start_polling(
        self,
        session_id: str,
        polling_coroutine,
        connection_type: ConnectionType = "chat"
    ):
        """Запустить polling задачу для сессии"""
        polling_key = f"{connection_type}:{session_id}"
        
        # Если уже есть задача - остановим её
        if polling_key in self.polling_tasks:
            self.polling_tasks[polling_key].cancel()
        
        # Создаем новую задачу
        task = asyncio.create_task(polling_coroutine)
        self.polling_tasks[polling_key] = task
        logger.info(f"Polling запущен для {polling_key}")
    
    async def switch_session(
        self,
        old_session_id: str,
        new_session_id: str,
        connection_type: ConnectionType = "chat"
    ):
        """Переключить сессию (например при смене чата)"""
        if old_session_id in self.connections[connection_type]:
            websocket = self.connections[connection_type][old_session_id]
            
            # Удаляем старое соединение
            del self.connections[connection_type][old_session_id]
            
            # Добавляем под новым ID
            self.connections[connection_type][new_session_id] = websocket
            
            # Останавливаем старый polling
            old_key = f"{connection_type}:{old_session_id}"
            if old_key in self.polling_tasks:
                self.polling_tasks[old_key].cancel()
                del self.polling_tasks[old_key]
            
            logger.info(f"Сессия переключена: {old_session_id} → {new_session_id}")


# Глобальный экземпляр менеджера
websocket_manager = WebSocketManager()


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, session_id: str = None):
    """WebSocket endpoint для уведомлений"""
    
    if not session_id:
        session_id = websocket.cookies.get("session_id", "anonymous")

    await websocket_manager.connect(websocket, session_id, "notifications")

    try:
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        websocket_manager.disconnect(session_id, "notifications")
    except Exception as e:
        logger.error(f"WebSocket ошибка для notifications:{session_id}: {e}")
        websocket_manager.disconnect(session_id, "notifications")


async def notify_model_updated(
    model_type: str, 
    model_id: str, 
    session_id: Optional[str] = None
):
    """Уведомить об обновлении модели"""
    message = {
        "type": "MODEL_UPDATED",
        "data": {"model_type": model_type, "model_id": model_id},
    }

    if session_id:
        await websocket_manager.send_to_session(session_id, message, "notifications")
    else:
        await websocket_manager.send_to_all(message, "notifications")
