"""
Unit тесты для NotificationManager.

Канон: единственный путь доставки события до сокета — `deliver_platform_event`,
вызываемый tail-reader'ом шины `platform:events` (см. `core.events.consumer`).
В WS-фрейм уходит событие без поля ``delivery``.
"""

import asyncio
import json

import pytest

from core.events import PlatformEvent
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


def _event(
    user_id: str | None,
    event_type: str,
    payload: dict | None = None,
    *,
    company_id: str | None = None,
    broadcast: bool = False,
) -> PlatformEvent:
    delivery: dict[str, object] = {}
    if user_id is not None:
        delivery["user_ids"] = [user_id]
    if company_id is not None:
        delivery["company_id"] = company_id
    if broadcast:
        delivery["broadcast"] = True
    return PlatformEvent.model_validate(
        {
            "type": event_type,
            "payload": payload or {},
            "meta": {"source": "system"},
            "delivery": delivery,
        }
    )


def _ws_frame(event: PlatformEvent) -> dict:
    return json.loads(event.ws_frame_json())


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
    """Несколько подключений одного пользователя получают событие."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_123")
    await manager.connect(ws2, "user_123")
    await manager.connect(ws3, "user_123")

    assert len(manager._connections["user_123"]) == 3

    event = _event("user_123", "notify/test/system_received", {"kind": "system", "title": "Hello"})
    await manager.deliver_platform_event(event)

    expected_frame = _ws_frame(event)
    assert ws1.sent_messages == [expected_frame]
    assert ws2.sent_messages == [expected_frame]
    assert ws3.sent_messages == [expected_frame]


@pytest.mark.asyncio
async def test_ws_frame_excludes_delivery():
    """WS-фрейм не содержит поле delivery (внутренняя адресация)."""
    manager = NotificationManager()
    ws = MockWebSocket()
    await manager.connect(ws, "user_123")

    event = _event("user_123", "notify/test/system_received", {"kind": "system"})
    await manager.deliver_platform_event(event)

    assert len(ws.sent_messages) == 1
    assert "delivery" not in ws.sent_messages[0]
    assert ws.sent_messages[0]["type"] == "notify/test/system_received"


@pytest.mark.asyncio
async def test_domain_event_without_delivery_not_forwarded():
    """Событие с delivery=None — чисто доменное, в сокеты не уходит."""
    manager = NotificationManager()
    ws = MockWebSocket()
    await manager.connect(ws, "user_123")

    event = PlatformEvent.model_validate(
        {"type": "crm/entity/created", "payload": {"entity_id": "e1"}}
    )
    await manager.deliver_platform_event(event)

    assert ws.sent_messages == []


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
    """Доставка события пользователю без подключений — без ошибки, без сайд-эффектов."""
    manager = NotificationManager()
    event = _event("user_offline", "notify/test/system_received", {"kind": "system"})
    # Не должно бросать.
    await manager.deliver_platform_event(event)


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

    event = _event("user_123", "notify/test/system_received", {"kind": "system"})
    await manager.deliver_platform_event(event)

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

    stats = await manager.get_stats()

    assert stats["active_users"] == 2
    assert stats["total_connections"] == 3
    assert stats["tail_task_running"] is False


@pytest.mark.asyncio
async def test_multiple_users():
    """Адресация по delivery.user_ids: только сокеты этих пользователей получают событие."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_1")
    await manager.connect(ws3, "user_2")

    event_1 = _event("user_1", "notify/test/system_received", {"kind": "system", "title": "For user 1"})
    event_2 = _event("user_2", "notify/test/system_received", {"kind": "system", "title": "For user 2"})

    await manager.deliver_platform_event(event_1)
    await manager.deliver_platform_event(event_2)

    assert ws1.sent_messages == [_ws_frame(event_1)]
    assert ws2.sent_messages == [_ws_frame(event_1)]
    assert ws3.sent_messages == [_ws_frame(event_2)]


@pytest.mark.asyncio
async def test_multi_user_delivery_single_event():
    """Одно событие с несколькими user_ids доставляется каждому адресату."""
    manager = NotificationManager()

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1, "user_1")
    await manager.connect(ws2, "user_2")
    await manager.connect(ws3, "user_3")

    event = PlatformEvent.model_validate(
        {
            "type": "sync/message/created",
            "payload": {"message_id": "m1"},
            "delivery": {"user_ids": ["user_1", "user_2"]},
        }
    )
    await manager.deliver_platform_event(event)

    expected_frame = _ws_frame(event)
    assert ws1.sent_messages == [expected_frame]
    assert ws2.sent_messages == [expected_frame]
    assert ws3.sent_messages == []


@pytest.mark.asyncio
async def test_company_target_delivers_to_company_sockets_only():
    """delivery.company_id — фрейм уходит только сокетам, привязанным к компании."""
    manager = NotificationManager()

    ws_company = MockWebSocket()
    ws_other = MockWebSocket()
    await manager.connect(ws_company, "user_in_company", company_id="c1")
    await manager.connect(ws_other, "user_other", company_id="c2")

    event = _event(None, "crm/note/created", {"id": "n1"}, company_id="c1")
    await manager.deliver_platform_event(event)

    assert ws_company.sent_messages == [_ws_frame(event)]
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

    stats = await manager.get_stats()
    assert stats["active_users"] == 3
    assert stats["total_connections"] == 15
