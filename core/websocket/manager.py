"""
Универсальный WebSocket менеджер для всех типов соединений.
Поддерживает Redis pub/sub для межпроцессной коммуникации (воркер → FastAPI).
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

ConnectionType = Literal["chat", "notifications", "updates"]

REDIS_CHANNEL = "websocket_notifications"


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
        self._redis_listener_task: Optional[asyncio.Task] = None

    async def connect(
        self, 
        websocket: WebSocket, 
        session_id: str, 
        connection_type: ConnectionType = "notifications"
    ):
        """Подключить WebSocket (websocket.accept() должен быть вызван до этого)"""
        # НЕ вызываем accept() здесь - он должен быть вызван в роутере до вызова connect()
        # Просто добавляем в список соединений - роутер уже принял соединение
        
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
        
        if polling_key in self.polling_tasks:
            old_task = self.polling_tasks[polling_key]
            if not old_task.done():
                logger.warning(f"⚠️ Останавливаем старую polling задачу для {polling_key}")
                old_task.cancel()
        
        task = asyncio.create_task(polling_coroutine)
        self.polling_tasks[polling_key] = task
        
        def task_done_callback(t):
            try:
                if t.cancelled():
                    logger.info(f"🔄 Polling задача отменена: {polling_key}")
                elif t.exception():
                    logger.error(f"❌ Polling задача завершилась с ошибкой для {polling_key}: {t.exception()}", exc_info=True)
                else:
                    logger.info(f"✅ Polling задача завершена успешно: {polling_key}")
            except Exception as e:
                logger.error(f"❌ Ошибка в callback polling задачи {polling_key}: {e}")
        
        task.add_done_callback(task_done_callback)
        logger.info(f"🚀 Polling запущен для {polling_key}")
    
    def is_polling_active(self, session_id: str, connection_type: ConnectionType = "chat") -> bool:
        """Проверить активна ли polling задача для сессии"""
        polling_key = f"{connection_type}:{session_id}"
        if polling_key not in self.polling_tasks:
            return False
        
        task = self.polling_tasks[polling_key]
        return not task.done()
    
    def get_polling_status(self, session_id: str, connection_type: ConnectionType = "chat") -> dict:
        """Получить статус polling задачи"""
        polling_key = f"{connection_type}:{session_id}"
        has_connection = session_id in self.connections[connection_type]
        has_task = polling_key in self.polling_tasks
        
        status = {
            "session_id": session_id,
            "connection_type": connection_type,
            "has_connection": has_connection,
            "has_polling_task": has_task,
            "polling_active": False,
            "polling_status": "no_task"
        }
        
        if has_task:
            task = self.polling_tasks[polling_key]
            if task.done():
                status["polling_active"] = False
                if task.cancelled():
                    status["polling_status"] = "cancelled"
                elif task.exception():
                    status["polling_status"] = "error"
                    status["error"] = str(task.exception())
                else:
                    status["polling_status"] = "completed"
            else:
                status["polling_active"] = True
                status["polling_status"] = "running"
        
        return status
    
    async def switch_session(
        self,
        old_session_id: str,
        new_session_id: str,
        connection_type: ConnectionType = "chat"
    ):
        """Переключить сессию (например при смене чата)"""
        if old_session_id in self.connections[connection_type]:
            websocket = self.connections[connection_type][old_session_id]
            
            del self.connections[connection_type][old_session_id]
            self.connections[connection_type][new_session_id] = websocket
            
            old_key = f"{connection_type}:{old_session_id}"
            if old_key in self.polling_tasks:
                self.polling_tasks[old_key].cancel()
                del self.polling_tasks[old_key]
            
            logger.info(f"Сессия переключена: {old_session_id} → {new_session_id}")
    
    async def publish_to_redis(self, message: dict, connection_type: ConnectionType = "notifications"):
        """
        Публикует сообщение в Redis канал для межпроцессной коммуникации.
        Используется из воркера TaskIQ.
        """
        settings = get_settings()
        redis_url = settings.database.redis_url
        
        payload = json.dumps({
            "connection_type": connection_type,
            "message": message,
        })
        
        client = aioredis.from_url(redis_url)
        try:
            await client.publish(REDIS_CHANNEL, payload)
            logger.debug(f"Опубликовано в Redis: {message.get('type', 'unknown')}")
        finally:
            await client.aclose()
    
    async def start_redis_listener(self):
        """
        Запускает слушателя Redis pub/sub.
        Вызывается при старте FastAPI приложения.
        """
        if self._redis_listener_task is not None:
            return
        
        self._redis_listener_task = asyncio.create_task(self._redis_listener_loop())
        logger.info("Redis pub/sub listener запущен")
    
    async def stop_redis_listener(self):
        """Останавливает слушателя Redis"""
        if self._redis_listener_task:
            self._redis_listener_task.cancel()
            self._redis_listener_task = None
            logger.info("Redis pub/sub listener остановлен")
    
    async def _redis_listener_loop(self):
        """Основной цикл слушателя Redis"""
        settings = get_settings()
        redis_url = settings.database.redis_url
        
        while True:
            try:
                client = aioredis.from_url(redis_url)
                pubsub = client.pubsub()
                await pubsub.subscribe(REDIS_CHANNEL)
                
                logger.info(f"Подписан на Redis канал: {REDIS_CHANNEL}")
                
                async for raw_message in pubsub.listen():
                    if raw_message["type"] == "message":
                        try:
                            payload = json.loads(raw_message["data"])
                            connection_type = payload.get("connection_type", "notifications")
                            message = payload.get("message", {})
                            
                            await self.send_to_all(message, connection_type)
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга Redis сообщения: {e}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка Redis listener: {e}", exc_info=True)
                await asyncio.sleep(5)


# Глобальный экземпляр менеджера
websocket_manager = WebSocketManager()


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, session_id: str = None):
    """WebSocket endpoint для уведомлений"""
    
    if not session_id:
        session_id = websocket.cookies.get("session_id", "anonymous")

    # Принимаем WebSocket соединение перед вызовом connect()
    await websocket.accept()
    
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
