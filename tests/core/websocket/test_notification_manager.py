"""
Unit тесты для NotificationManager.

Канон: единственный путь доставки события до сокета — `_deliver_envelope`,
вызываемый из `_redis_loop` при получении конверта `{target, event}` из
канала `platform:ui_events` (см. `core.ui_events.dispatcher`).
"""

import asyncio
import json

import pytest

from core.ui_events.contract import UIEventEnvelope
from core.websocket.manager import NotificationManager


class MockWebSocket:
    """Мок WebSocket для тестирования"""

    def __init__(self):
        self.sent_messages: list[dict] = []
        self.closed = False

    async def send_text(self, message: str) -> None:
        self.sent_messages.append(json.loads(message))

    async def close(self, code=None, reason=None) -> None:
        self.closed = True


def _envelope(
    user_id: str | None,
    event_type: str,
    payload: dict | None = None,
    *,
    company_id: str | None = None,
    broadcast: bool = False,
) -> UIEventEnvelope:
    target: dict[str, object] = {}
    if user_id is not None:
        target["user_id"] = user_id
    if company_id is not None:
        target["company_id"] = company_id
    if broadcast:
        target["broadcast"] = True
    return UIEventEnvelope.model_validate(
        {
            "target": target,
            "event": {
                "type": event_type,
                "payload": payload or {},
                "meta": {"source": "system"},
            },
        }
    )


def _event_json(envelope: UIEventEnvelope) -> dict:
    return envelope.event.model_dump(mode="json")


@pytest.mark.asyncio
async def test_single_connection():
    """Один пользователь с одним подключением."""
    manager = NotificationManager()

    ws = MockWebSocket()
    await manager.connect(ws, "user_123")

    assert "user_123" in manager._connections
    assert len(manager._connections["user_123"]) == 1

    await manager.disconnect(ws, "user_123")

    assert "user_123" not in manager._connections


@pytest.mark.asyncio
async def test_multiple_connections_same_user():
    """Несколько подключений одного пользователя получают envelope."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")
    await manager.connect(ws3, "user_123")

    assert len(manager._connections["user_123"]) == 3

    envelope = _envelope("user_123", "notify/test/system_received", {"kind": "system", "title": "Hello"})
    await manager._deliver_envelope(envelope)

    expected_event = _event_json(envelope)
    assert ws1.sent_messages == [expected_event]
    assert ws2.sent_messages == [expected_event]
    assert ws3.sent_messages == [expected_event]


@pytest.mark.asyncio
async def test_disconnect_one_connection():
    """Отключение одного из нескольких подключений."""
    manager = NotificationManager()

    ws1, ws2 = MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")

    assert len(manager._connections["user_123"]) == 2

    await manager.disconnect(ws1, "user_123")

    assert len(manager._connections["user_123"]) == 1
    assert ws2 in manager._connections["user_123"]
    assert ws1 not in manager._connections["user_123"]


@pytest.mark.asyncio
async def test_send_to_offline_user():
    """Доставка envelope пользователю без подключений — без ошибки, без сайд-эффектов."""
    manager = NotificationManager()
    envelope = _envelope("user_offline", "notify/test/system_received", {"kind": "system"})
    # Не должно бросать.
    await manager._deliver_envelope(envelope)


@pytest.mark.asyncio
async def test_dead_connection_cleanup():
    """Если send_text падает — мёртвый сокет вычищается из реестра."""
    manager = NotificationManager()

    ws1, ws2 = MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")

    async def failing_send(message):
        raise Exception("Connection lost")

    ws1.send_text = failing_send

    envelope = _envelope("user_123", "notify/test/system_received", {"kind": "system"})
    await manager._deliver_envelope(envelope)

    assert len(manager._connections["user_123"]) == 1
    assert ws2 in manager._connections["user_123"]
    assert ws1 not in manager._connections["user_123"]


@pytest.mark.asyncio
async def test_get_stats():
    """Статистика подключений."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_1")
    await manager.connect(ws3, "user_2")

    stats = manager.get_stats()

    assert stats["active_users"] == 2
    assert stats["total_connections"] == 3
    assert stats["redis_connected"] is False


@pytest.mark.asyncio
async def test_multiple_users():
    """Адресация по target.user_id: только сокеты этого пользователя получают envelope."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_1")
    await manager.connect(ws3, "user_2")

    env_1 = _envelope("user_1", "notify/test/system_received", {"kind": "system", "title": "For user 1"})
    env_2 = _envelope("user_2", "notify/test/system_received", {"kind": "system", "title": "For user 2"})

    await manager._deliver_envelope(env_1)
    await manager._deliver_envelope(env_2)

    assert ws1.sent_messages == [_event_json(env_1)]
    assert ws2.sent_messages == [_event_json(env_1)]
    assert ws3.sent_messages == [_event_json(env_2)]


@pytest.mark.asyncio
async def test_company_target_delivers_to_company_sockets_only():
    """target.company_id — фрейм уходит только сокетам, привязанным к компании."""
    manager = NotificationManager()

    ws_company = MockWebSocket()
    ws_other = MockWebSocket()
    await manager.connect(ws_company, "user_in_company", company_id="c1")
    await manager.connect(ws_other, "user_other", company_id="c2")

    env = _envelope(None, "crm/note/created", {"id": "n1"}, company_id="c1")
    await manager._deliver_envelope(env)

    assert ws_company.sent_messages == [_event_json(env)]
    assert ws_other.sent_messages == []


@pytest.mark.asyncio
async def test_concurrent_connections():
    """Одновременные подключения."""
    manager = NotificationManager()

    async def connect_user(user_id: str, count: int):
        sockets = []
        for _ in range(count):
            ws = MockWebSocket()
            await manager.connect(ws, user_id)
            sockets.append(ws)
        return sockets

    await asyncio.gather(
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
