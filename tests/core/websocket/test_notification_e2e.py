"""E2E notify_user → bus → Centrifugo publication (PlatformEvent)."""

from __future__ import annotations

import pytest

from core.realtime.presence import fetch_user_presence
from core.websocket.publisher import Notification, NotificationType, notify_user
from tests.realtime.centrifugo_ws import connect_centrifugo, wait_platform_event


def _expected_event_type(service: str, notification_type: NotificationType) -> str:
    return f"notify/{service}/{notification_type.value}_received"


def _event_payload(event: dict[str, object]) -> dict[str, object]:
    payload_raw = event.get("payload")
    if not isinstance(payload_raw, dict):
        raise AssertionError("WS event payload must be an object")
    return payload_raw


def _payload_data(payload: dict[str, object]) -> dict[str, object]:
    data_raw = payload.get("data")
    if not isinstance(data_raw, dict):
        raise AssertionError("notification payload.data must be an object")
    return data_raw


@pytest.mark.asyncio
async def test_single_websocket_notification(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
    unique_id: str,
) -> None:
    _ = crm_client
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)
    expected_title = f"Тестовое уведомление {unique_id}"

    async with connect_centrifugo(auth_token_system) as ws:
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=expected_title,
                message="Проверка работы WebSocket",
                service="test",
                priority="normal",
            ),
        )
        event = await wait_platform_event(
            ws,
            type_=expected_type,
            where={"title": expected_title},
            timeout=15.0,
        )
        payload = _event_payload(dict(event))
        assert payload["service"] == "test"
        assert payload["kind"] == NotificationType.SYSTEM.value


@pytest.mark.asyncio
async def test_multiple_tabs_same_user(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
    unique_id: str,
) -> None:
    _ = crm_client
    expected_type = _expected_event_type("crm", NotificationType.MENTION)
    expected_title = f"Multi-tab mention {unique_id}"

    async with (
        connect_centrifugo(auth_token_system) as ws1,
        connect_centrifugo(auth_token_system) as ws2,
        connect_centrifugo(auth_token_system) as ws3,
    ):
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.MENTION,
                title=expected_title,
                message="Пользователь упомянул вас в заметке",
                service="crm",
                priority="high",
            ),
        )
        ev1 = await wait_platform_event(ws1, type_=expected_type, where={"title": expected_title}, timeout=15)
        ev2 = await wait_platform_event(ws2, type_=expected_type, where={"title": expected_title}, timeout=15)
        ev3 = await wait_platform_event(ws3, type_=expected_type, where={"title": expected_title}, timeout=15)
        assert ev1["type"] == ev2["type"] == ev3["type"] == expected_type


@pytest.mark.asyncio
async def test_access_request_notification_flow(
    crm_client,
    unique_id,
    auth_headers_system,
    auth_token_system,
    system_user_id,
    crm_service,
) -> None:
    entity_resp = await crm_client.post(
        "/crm/api/v1/entities",
        json={
            "entity_type": "note",
            "name": f"Private note {unique_id}",
            "description": "Секретная заметка",
            "user_id": system_user_id,
        },
        headers=auth_headers_system,
    )

    entity = entity_resp.json()
    entity_id = entity["entity_id"]
    expected_type = _expected_event_type("crm", NotificationType.ACCESS_REQUEST)

    async with connect_centrifugo(auth_token_system) as ws_owner:
        request_resp = await crm_client.post(
            "/crm/api/v1/access-requests",
            json={
                "resource_type": "entity",
                "resource_id": entity_id,
                "message": f"Нужен доступ для тестирования {unique_id}",
            },
            headers=auth_headers_system,
        )
        assert request_resp.status_code == 200
        access_request_id = request_resp.json()["access_request_id"]
        event = await wait_platform_event(ws_owner, type_=expected_type, timeout=15)
        payload = _event_payload(dict(event))
        data = _payload_data(payload)
        assert payload["title"] == "Новый запрос доступа"
        assert entity_id in str(data["entity_id"])
        assert data["access_request_id"] == access_request_id


@pytest.mark.asyncio
async def test_websocket_reconnection(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
    unique_id: str,
) -> None:
    _ = crm_client
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)
    expected_title = f"После переподключения {unique_id}"

    async with connect_centrifugo(auth_token_system) as ws1:
        _ = ws1

    async with connect_centrifugo(auth_token_system) as ws2:
        await notify_user(
            user_id=system_user_id,
            notification=Notification(
                type=NotificationType.SYSTEM,
                title=expected_title,
                message="Уведомление после разрыва",
                service="test",
            ),
        )
        event = await wait_platform_event(
            ws2, type_=expected_type, where={"title": expected_title}, timeout=15
        )
        assert _event_payload(dict(event))["title"] == expected_title


@pytest.mark.asyncio
async def test_notification_priority_levels(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
) -> None:
    _ = crm_client
    expected_type = _expected_event_type("test", NotificationType.SYSTEM)

    async with connect_centrifugo(auth_token_system) as ws:
        for priority in ("low", "normal", "high", "urgent"):
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
            event = await wait_platform_event(
                ws, type_=expected_type, where={"title": expected_title}, timeout=20
            )
            payload = _event_payload(dict(event))
            assert payload["priority"] == priority


@pytest.mark.asyncio
async def test_notification_with_action_url(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
) -> None:
    _ = crm_client
    expected_type = _expected_event_type("crm", NotificationType.TASK_COMPLETED)

    async with connect_centrifugo(auth_token_system) as ws:
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
        event = await wait_platform_event(
            ws, type_=expected_type, where={"title": "Задача завершена"}, timeout=20
        )
        payload = _event_payload(dict(event))
        assert payload["action_url"] == "/crm/tasks/task_123"
        assert _payload_data(payload)["task_id"] == "task_123"


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_notification_types_coverage(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
) -> None:
    _ = crm_client
    notification_types = [
        NotificationType.ACCESS_REQUEST,
        NotificationType.ENTITY_UPDATED,
        NotificationType.TASK_COMPLETED,
        NotificationType.MENTION,
        NotificationType.SYSTEM,
        NotificationType.SYNC_NEW_MESSAGE,
    ]

    async with connect_centrifugo(auth_token_system) as ws:
        for notif_type in notification_types:
            title = f"types-cov-{system_user_id}-{notif_type.value}"
            await notify_user(
                user_id=system_user_id,
                notification=Notification(
                    type=notif_type,
                    title=title,
                    message=f"Testing notification type {notif_type.value}",
                    service="test",
                ),
            )
            event = await wait_platform_event(
                ws,
                type_=_expected_event_type("test", notif_type),
                where={"title": title},
                timeout=15.0,
            )
            assert _event_payload(dict(event))["kind"] == notif_type.value


@pytest.mark.asyncio
async def test_centrifugo_presence_stats(
    crm_client,
    auth_token_system,
    system_user_id,
    crm_service,
) -> None:
    _ = crm_client, crm_service
    async with (
        connect_centrifugo(auth_token_system) as ws1,
        connect_centrifugo(auth_token_system) as ws2,
        connect_centrifugo(auth_token_system) as ws3,
    ):
        _ = ws1, ws2, ws3
        snapshot = await fetch_user_presence(system_user_id, company_id="system")
        assert snapshot.connected is True
        assert snapshot.num_clients >= 3
