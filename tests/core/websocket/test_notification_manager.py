"""
Unit тесты для NotificationManager.
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock

from core.websocket.manager import NotificationManager


class MockWebSocket:
    """Мок WebSocket для тестирования"""

    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def send_text(self, message: str):
        """Сохраняет отправленные сообщения"""
        self.sent_messages.append(json.loads(message))

    async def close(self, code=None, reason=None):
        """Помечает как закрытый"""
        self.closed = True


@pytest.mark.asyncio
async def test_single_connection():
    """Один пользователь с одним подключением"""
    manager = NotificationManager()

    ws = MockWebSocket()
    await manager.connect(ws, "user_123")

    assert "user_123" in manager._connections
    assert len(manager._connections["user_123"]) == 1

    await manager.disconnect(ws, "user_123")

    assert "user_123" not in manager._connections


@pytest.mark.asyncio
async def test_multiple_connections_same_user():
    """Несколько подключений одного пользователя"""
    manager = NotificationManager()

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")
    await manager.connect(ws3, "user_123")

    assert len(manager._connections["user_123"]) == 3

    notification = {"type": "test", "message": "Hello"}
    await manager.send_to_user("user_123", notification)

    assert ws1.sent_messages == [notification]
    assert ws2.sent_messages == [notification]
    assert ws3.sent_messages == [notification]


@pytest.mark.asyncio
async def test_disconnect_one_connection():
    """Отключение одного из нескольких подключений"""
    manager = NotificationManager()

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")

    assert len(manager._connections["user_123"]) == 2

    await manager.disconnect(ws1, "user_123")

    assert len(manager._connections["user_123"]) == 1
    assert ws2 in manager._connections["user_123"]
    assert ws1 not in manager._connections["user_123"]


@pytest.mark.asyncio
async def test_send_to_offline_user():
    """Отправка уведомления пользователю без подключений"""
    manager = NotificationManager()

    notification = {"type": "test", "message": "Hello"}
    await manager.send_to_user("user_offline", notification)


@pytest.mark.asyncio
async def test_dead_connection_cleanup():
    """Очистка мертвых соединений"""
    manager = NotificationManager()

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")

    async def failing_send(message):
        raise Exception("Connection lost")

    ws1.send_text = failing_send

    notification = {"type": "test", "message": "Hello"}
    await manager.send_to_user("user_123", notification)

    assert len(manager._connections["user_123"]) == 1
    assert ws2 in manager._connections["user_123"]
    assert ws1 not in manager._connections["user_123"]


@pytest.mark.asyncio
async def test_get_stats():
    """Получение статистики подключений"""
    manager = NotificationManager()

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_1")
    await manager.connect(ws3, "user_2")

    stats = manager.get_stats()

    assert stats["active_users"] == 2
    assert stats["total_connections"] == 3
    assert stats["redis_connected"] is False


@pytest.mark.asyncio
async def test_multiple_users():
    """Несколько пользователей с разными подключениями"""
    manager = NotificationManager()

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_1")
    await manager.connect(ws3, "user_2")

    notification_1 = {"type": "test", "message": "For user 1"}
    notification_2 = {"type": "test", "message": "For user 2"}

    await manager.send_to_user("user_1", notification_1)
    await manager.send_to_user("user_2", notification_2)

    assert ws1.sent_messages == [notification_1]
    assert ws2.sent_messages == [notification_1]
    assert ws3.sent_messages == [notification_2]


@pytest.mark.asyncio
async def test_concurrent_connections():
    """Одновременные подключения"""
    manager = NotificationManager()

    async def connect_user(user_id: str, count: int):
        sockets = []
        for i in range(count):
            ws = MockWebSocket()
            await manager.connect(ws, user_id)
            sockets.append(ws)
        return sockets

    users_sockets = await asyncio.gather(
        connect_user("user_1", 5),
        connect_user("user_2", 3),
        connect_user("user_3", 7),
    )

    assert len(manager._connections["user_1"]) == 5
    assert len(manager._connections["user_2"]) == 3
    assert len(manager._connections["user_3"]) == 7

    stats = manager.get_stats()
    assert stats["active_users"] == 3
    assert stats["total_connections"] == 15

