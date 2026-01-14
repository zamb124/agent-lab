"""
Менеджер WebSocket уведомлений для всех сервисов платформы.

Ключевые особенности:
- User-centric: группировка по user_id, поддержка N подключений одного пользователя
- Redis Pub/Sub: межпроцессная коммуникация (воркеры → FastAPI → WebSocket)
- Ephemeral: уведомления не хранятся, только real-time доставка
"""

import asyncio
import json
from typing import Dict, Set, Optional
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import WebSocket

from core.logging import get_logger

logger = get_logger(__name__)

REDIS_CHANNEL = "platform:notifications"


class NotificationManager:
    """Менеджер WebSocket уведомлений для всех сервисов"""

    def __init__(self):
        # user_id -> Set[WebSocket]
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._connection_lock = asyncio.Lock()
        self._redis_task: Optional[asyncio.Task] = None
        self._redis_client: Optional[aioredis.Redis] = None

    async def connect(self, websocket: WebSocket, user_id: str):
        """Добавить WebSocket подключение для user_id"""
        async with self._connection_lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
            logger.info(
                f"WS подключен: user={user_id}, всего подключений={len(self._connections[user_id])}"
            )

    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Удалить конкретное WebSocket подключение"""
        async with self._connection_lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
                    logger.info(f"WS отключен: user={user_id}, последнее подключение")
                else:
                    logger.info(
                        f"WS отключен: user={user_id}, осталось={len(self._connections[user_id])}"
                    )

    async def send_to_user(self, user_id: str, notification: dict):
        """Отправить уведомление во ВСЕ подключения пользователя"""
        if user_id not in self._connections:
            logger.debug(f"User {user_id} не подключен, уведомление пропущено")
            return

        dead_connections = []
        message = json.dumps(notification)
        sent_count = 0

        for ws in self._connections[user_id]:
            try:
                await ws.send_text(message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Не удалось отправить в WS для user {user_id}: {e}")
                dead_connections.append(ws)

        logger.info(
            f"Уведомление отправлено user={user_id} в {sent_count} подключений, "
            f"тип={notification.get('type', 'unknown')}"
        )

        if dead_connections:
            async with self._connection_lock:
                for ws in dead_connections:
                    self._connections[user_id].discard(ws)
                if not self._connections[user_id]:
                    del self._connections[user_id]

    async def publish(self, user_id: str, notification: dict):
        """Опубликовать уведомление в Redis (для межпроцессной доставки)"""
        if not self._redis_client:
            raise RuntimeError("Redis client not initialized")

        payload = json.dumps(
            {
                "user_id": user_id,
                "notification": notification,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        await self._redis_client.publish(REDIS_CHANNEL, payload)
        logger.debug(f"Уведомление опубликовано в Redis: user={user_id}, type={notification.get('type')}")

    async def start_redis_listener(self, redis_url: str):
        """Запустить Redis Pub/Sub listener"""
        if self._redis_task:
            logger.warning("Redis listener уже запущен")
            return

        self._redis_client = aioredis.from_url(redis_url)
        self._redis_task = asyncio.create_task(self._redis_loop())
        logger.info("Redis listener для уведомлений запущен")

    async def stop_redis_listener(self):
        """Остановить Redis listener"""
        if self._redis_task:
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass
            self._redis_task = None
            logger.info("Redis listener остановлен")

        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None

    async def _redis_loop(self):
        """Основной цикл прослушивания Redis"""
        pubsub = self._redis_client.pubsub()
        await pubsub.subscribe(REDIS_CHANNEL)
        logger.info(f"Подписка на Redis канал: {REDIS_CHANNEL}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        user_id = data["user_id"]
                        notification = data["notification"]

                        await self.send_to_user(user_id, notification)
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга Redis сообщения: {e}")
                    except Exception as e:
                        logger.error(f"Ошибка обработки уведомления: {e}", exc_info=True)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(REDIS_CHANNEL)
            raise
        except Exception as e:
            logger.error(f"Критическая ошибка в Redis listener: {e}", exc_info=True)
            raise

    def is_user_connected(self, user_id: str) -> bool:
        """Проверить есть ли активные WebSocket подключения пользователя"""
        return user_id in self._connections and len(self._connections[user_id]) > 0

    def get_stats(self) -> dict:
        """Получить статистику подключений"""
        return {
            "active_users": len(self._connections),
            "total_connections": sum(
                len(ws_set) for ws_set in self._connections.values()
            ),
            "redis_connected": self._redis_client is not None,
            "redis_task_running": self._redis_task is not None
            and not self._redis_task.done(),
        }


notification_manager = NotificationManager()
