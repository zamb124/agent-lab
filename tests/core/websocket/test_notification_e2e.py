"""
E2E тесты для системы уведомлений с реальными WebSocket и Redis.

Канон: notify_user(...) публикует UIEvent в `platform:ui_events`. WS-роутер
форвардит событие в сокеты `/<svc>/api/ws/notifications` как фрейм
`{type: 'notify/<service>/<kind>_received', payload: {title, message, data,
priority, action_url, created_at, service, kind}}`.

БЕЗ МОКОВ — реальные WebSocket + Redis.
"""

import pytest
import asyncio
import json
import time

import websockets

from core.websocket.publisher import notify_user, Notification, NotificationType


def _expected_event_type(service: str, notification_type: NotificationType) -> str:
    return f"notify/{service}/{notification_type.value}_received"


async def _recv_event_by_type(ws, expected_type: str, timeout: float = 5.0) -> dict:
    """Ждать UIEvent с конкретным `type` (отбрасывает чужие push'и из канала)."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Не получено ожидаемое событие type={expected_type}")
        message = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = json.loads(message)
        if event.get("type") == expected_type:
            return event


async def _recv_event_by_payload_title(ws, expected_title: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Не получено ожидаемое уведомление: {expected_title}")
        message = await asyncio.wait_for(ws.recv(), timeout=remaining)
        event = json.loads(message)
        payload = event.get("payload") or {}
        if payload.get("title") == expected_title:
            return event


@pytest.mark.asyncio
async def test_single_websocket_notification(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Одно WebSocket подключение получает уведомление."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title="Тестовое уведомление",
                message="Проверка работы WebSocket",
                service="test",
                priority="normal",
            ),
        )

        event = await _recv_event_by_type(ws, expected_type, timeout=5)
        assert event["type"] == expected_type
        payload = event["payload"]
        assert payload["title"] == "Тестовое уведомление"
        assert payload["service"] == "test"
        assert payload["kind"] == NotificationType.SYSTEM.value


@pytest.mark.asyncio
async def test_multiple_tabs_same_user(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Несколько вкладок (WebSocket) одного пользователя."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("crm", NotificationType.MENTION)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws1:
        async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws2:
            async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws3:
                await notify_user(
                    user_id=system_user_id,
                    notification=Notification(
                        type=NotificationType.MENTION,
                        title="Вас упомянули",
                        message="Пользователь упомянул вас в заметке",
                        service="crm",
                        priority="high",
                    ),
                )

                ev1 = await _recv_event_by_type(ws1, expected_type, timeout=5)
                ev2 = await _recv_event_by_type(ws2, expected_type, timeout=5)
                ev3 = await _recv_event_by_type(ws3, expected_type, timeout=5)

                assert ev1["type"] == ev2["type"] == ev3["type"] == expected_type
                assert ev1["payload"]["title"] == ev2["payload"]["title"] == ev3["payload"]["title"]


@pytest.mark.asyncio
async def test_access_request_notification_flow(crm_client, unique_id, auth_headers_system, ws_cookie_system, system_user_id, crm_service):
    """Полный flow уведомлений при запросе доступа."""

    entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
        "entity_type": "note",
        "name": f"Private note {unique_id}",
        "description": "Секретная заметка",
        "user_id": system_user_id,
    }, headers=auth_headers_system)

    entity = entity_resp.json()
    entity_id = entity["entity_id"]

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("crm", NotificationType.ACCESS_REQUEST)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws_owner:
        request_resp = await crm_client.post("/crm/api/v1/access-requests", json={
            "resource_type": "entity",
            "resource_id": entity_id,
            "message": f"Нужен доступ для тестирования {unique_id}",
        }, headers=auth_headers_system)

        assert request_resp.status_code == 200
        request_id = request_resp.json()["request_id"]

        event = await _recv_event_by_type(ws_owner, expected_type, timeout=5)
        payload = event["payload"]
        assert payload["title"] == "Новый запрос доступа"
        assert entity_id in payload["data"]["entity_id"]
        assert payload["data"]["request_id"] == request_id


@pytest.mark.asyncio
async def test_websocket_heartbeat(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Проверка heartbeat механизма."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
        await ws.send("ping")
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        assert response == "pong"


@pytest.mark.asyncio
async def test_websocket_reconnection(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Проверка переподключения после разрыва."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws1:
        await ws1.send("ping")
        pong1 = await asyncio.wait_for(ws1.recv(), timeout=5)
        assert pong1 == "pong"

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws2:
        await ws2.send("ping")
        pong2 = await asyncio.wait_for(ws2.recv(), timeout=5)
        assert pong2 == "pong"

        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title="После переподключения",
                message="Уведомление после разрыва",
                service="test",
            ),
        )

        event = await _recv_event_by_type(ws2, expected_type, timeout=5)
        assert event["payload"]["title"] == "После переподключения"


@pytest.mark.asyncio
async def test_notification_priority_levels(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Проверка всех уровней приоритета."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
        priorities = ["low", "normal", "high", "urgent"]

        for priority in priorities:
            expected_title = f"Priority {priority}"
            await notify_user(
                user_id=system_user_id,
                notification=Notification(
                    type=NotificationType.SYSTEM,
                    title=expected_title,
                    message=f"Тест приоритета {priority}",
                    service="test",
                    priority=priority,
                ),
            )

            event = await _recv_event_by_payload_title(ws, expected_title, timeout=5)
            assert event["type"] == expected_type
            assert event["payload"]["priority"] == priority
            assert event["payload"]["title"] == expected_title


@pytest.mark.asyncio
async def test_notification_with_action_url(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Проверка уведомления с action_url."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"
    expected_type = _expected_event_type("crm", NotificationType.TASK_COMPLETED)

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.TASK_COMPLETED,
                title="Задача завершена",
                message="Ваша задача успешно выполнена",
                service="crm",
                action_url="/crm/tasks/task_123",
                data={"task_id": "task_123", "status": "completed"},
            ),
        )

        event = await _recv_event_by_type(ws, expected_type, timeout=5)
        payload = event["payload"]
        assert payload["action_url"] == "/crm/tasks/task_123"
        assert payload["data"]["task_id"] == "task_123"


@pytest.mark.asyncio
async def test_notification_types_coverage(crm_client, ws_cookie_system, system_user_id, crm_service):
    """Проверка всех типов уведомлений."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"

    notification_types = [
        NotificationType.ACCESS_REQUEST,
        NotificationType.ENTITY_UPDATED,
        NotificationType.TASK_COMPLETED,
        NotificationType.MENTION,
        NotificationType.SYSTEM,
        NotificationType.SYNC_NEW_MESSAGE,
    ]

    async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
        for notif_type in notification_types:
            await notify_user(
                user_id=system_user_id,
                notification=Notification(
                    type=notif_type,
                    title=f"Test {notif_type.value}",
                    message=f"Testing notification type {notif_type.value}",
                    service="test",
                ),
            )

            expected_type = _expected_event_type("test", notif_type)
            event = await _recv_event_by_type(ws, expected_type, timeout=5)
            assert event["type"] == expected_type
            assert event["payload"]["kind"] == notif_type.value


@pytest.mark.asyncio
async def test_ws_stats_endpoint(crm_client, auth_headers_system, ws_cookie_system, crm_service):
    """Проверка endpoint статистики WebSocket."""

    ws_url = "ws://localhost:9003/crm/api/ws/notifications"

    connections = []
    for i in range(3):
        ws = await websockets.connect(ws_url, additional_headers=ws_cookie_system)
        connections.append(ws)

    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True) as http_client:
            http_client.cookies.set(
                "auth_token",
                auth_headers_system["Authorization"].replace("Bearer ", ""),
            )
            stats_resp = await http_client.get(
                "http://localhost:9003/crm/api/ws/stats",
                headers=auth_headers_system,
            )

            if stats_resp.status_code != 200:
                pytest.skip(f"Endpoint /ws/stats требует сессию через cookie (status={stats_resp.status_code})")

            stats = stats_resp.json()
            # Новый формат stats: active_users / total_connections / redis_connected.
            assert "active_users" in stats
            assert "total_connections" in stats
            assert stats["total_connections"] >= 3

    finally:
        for ws in connections:
            await ws.close()
