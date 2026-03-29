"""
Покрытие backend-функций платформенного календаря (без внешних интеграций).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.calendar.service import CalendarService


def _range_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        (now - timedelta(days=30)).isoformat(),
        (now + timedelta(days=30)).isoformat(),
    )


@pytest.mark.asyncio
async def test_calendar_event_crud_and_filters(
    unique_id: str,
    frontend_client,
    auth_headers_system,
) -> None:
    start_at = datetime.now(timezone.utc) + timedelta(hours=2)
    end_at = start_at + timedelta(hours=1)
    create_payload = {
        "title": f"Calendar CRUD {unique_id}",
        "kind": "meeting",
        "source": "platform",
        "source_id": None,
        "namespace": "tests",
        "description": "Initial description",
        "location": "Room 101",
        "status": "confirmed",
        "timezone": "UTC",
        "all_day": False,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "attendees": [{"email": f"user-{unique_id}@example.com"}],
        "recurrence_rule": None,
        "recurrence_id": None,
        "series_id": None,
        "deep_link": "/sync",
        "metadata": {"case": unique_id},
    }
    create_response = await frontend_client.post(
        "/frontend/api/calendar/events",
        json=create_payload,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200
    created_event = create_response.json()
    event_id = created_event["event_id"]

    update_payload = {**create_payload, "title": f"Calendar CRUD updated {unique_id}", "location": "Room 202"}
    update_response = await frontend_client.put(
        f"/frontend/api/calendar/events/{event_id}",
        json=update_payload,
        headers=auth_headers_system,
    )
    assert update_response.status_code == 200
    updated_event = update_response.json()
    assert updated_event["title"] == f"Calendar CRUD updated {unique_id}"
    assert updated_event["location"] == "Room 202"
    assert updated_event["event_id"] == event_id

    list_start, list_end = _range_window()
    list_response = await frontend_client.post(
        "/frontend/api/calendar/events/list",
        json={
            "start_at": list_start,
            "end_at": list_end,
            "include_sources": ["platform"],
            "limit": 2000,
        },
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    list_data = list_response.json()
    events = list_data["events"]
    assert any(item["event_id"] == event_id for item in events)

    delete_response = await frontend_client.delete(
        f"/frontend/api/calendar/events/{event_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    after_delete = await frontend_client.post(
        "/frontend/api/calendar/events/list",
        json={
            "start_at": list_start,
            "end_at": list_end,
            "include_sources": ["platform"],
            "limit": 2000,
        },
        headers=auth_headers_system,
    )
    assert after_delete.status_code == 200
    event_ids = {item["event_id"] for item in after_delete.json()["events"]}
    assert event_id not in event_ids


@pytest.mark.asyncio
async def test_calendar_rejects_invalid_time_ranges(
    unique_id: str,
    frontend_client,
    auth_headers_system,
) -> None:
    now = datetime.now(timezone.utc)
    invalid_event_response = await frontend_client.post(
        "/frontend/api/calendar/events",
        json={
            "title": f"Invalid range {unique_id}",
            "kind": "event",
            "source": "platform",
            "source_id": None,
            "namespace": None,
            "description": None,
            "location": None,
            "status": "confirmed",
            "timezone": "UTC",
            "all_day": False,
            "start_at": (now + timedelta(hours=3)).isoformat(),
            "end_at": (now + timedelta(hours=2)).isoformat(),
            "attendees": [],
            "recurrence_rule": None,
            "recurrence_id": None,
            "series_id": None,
            "deep_link": None,
            "metadata": {},
        },
        headers=auth_headers_system,
    )
    assert invalid_event_response.status_code == 400

    invalid_list_response = await frontend_client.post(
        "/frontend/api/calendar/events/list",
        json={
            "start_at": (now + timedelta(days=1)).isoformat(),
            "end_at": (now - timedelta(days=1)).isoformat(),
            "include_sources": ["platform"],
            "limit": 100,
        },
        headers=auth_headers_system,
    )
    assert invalid_list_response.status_code == 400


@pytest.mark.asyncio
async def test_calendar_google_oauth_start_redirects_to_provider(
    frontend_client,
    auth_headers_system,
    monkeypatch,
) -> None:
    async def fake_start_google_oauth(
        self,
        user_id: str,
        company_id: str,
        redirect_uri: str,
        return_path: str,
    ) -> str:
        _ = (self, user_id, company_id, redirect_uri, return_path)
        return "https://accounts.google.com/o/oauth2/v2/auth?state=test-state"

    monkeypatch.setattr(CalendarService, "start_google_oauth", fake_start_google_oauth)

    response = await frontend_client.get(
        "/frontend/api/calendar/integrations/google/start",
        params={"return_path": "/crm/calendar"},
        headers=auth_headers_system,
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers.get("location")
    assert location == "https://accounts.google.com/o/oauth2/v2/auth?state=test-state"


@pytest.mark.asyncio
async def test_calendar_google_oauth_callback_redirects_to_return_path(
    frontend_client,
    auth_headers_system,
    monkeypatch,
) -> None:
    async def fake_complete_google_oauth(
        self,
        state: str,
        code: str,
    ) -> str:
        _ = (self, state, code)
        return "/crm/calendar?view=month"

    monkeypatch.setattr(CalendarService, "complete_google_oauth", fake_complete_google_oauth)

    response = await frontend_client.get(
        "/frontend/api/calendar/integrations/google/callback",
        params={"state": "state-1", "code": "code-1"},
        headers=auth_headers_system,
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers.get("location")
    assert location is not None
    assert "calendar_provider=google" in location
    assert "calendar_status=connected" in location
    assert location.startswith("/crm/calendar?view=month")


@pytest.mark.asyncio
async def test_auth_google_callback_can_finalize_calendar_integration_state(
    frontend_client,
    monkeypatch,
) -> None:
    async def fake_complete_google_oauth(self, state: str, code: str) -> str:
        _ = (self, state, code)
        return "/crm/calendar"

    monkeypatch.setattr(CalendarService, "complete_google_oauth", fake_complete_google_oauth)

    response = await frontend_client.get(
        "/auth/callback/google",
        params={"state": "calendar-state", "code": "calendar-code"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 307}
    location = response.headers.get("location")
    assert location is not None
    assert location.startswith("/crm/calendar")
    assert "calendar_provider=google" in location
    assert "calendar_status=connected" in location


@pytest.mark.asyncio
async def test_calendar_yandex_connect_requires_username(
    unique_id: str,
    frontend_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    response = await frontend_client.post(
        "/frontend/api/calendar/integrations/connect",
        json={
            "provider": "yandex",
            "access_token": "app-password",
            "refresh_token": None,
            "expires_at": None,
            "scope": None,
            "token_type": None,
            "default_calendar_id": "default",
            "sync_enabled": True,
            "sync_inbound_enabled": True,
            "sync_outbound_enabled": True,
        },
        headers=auth_headers_system,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_calendar_integration_notifications_flag_roundtrip(
    unique_id: str,
    frontend_client,
    auth_headers_system,
) -> None:
    connect_response = await frontend_client.post(
        "/frontend/api/calendar/integrations/connect",
        json={
            "provider": "yandex",
            "username": f"user-{unique_id}@yandex.ru",
            "access_token": "app-password",
            "refresh_token": None,
            "expires_at": None,
            "scope": None,
            "token_type": None,
            "default_calendar_id": "default",
            "sync_enabled": True,
            "sync_inbound_enabled": True,
            "sync_outbound_enabled": True,
            "notifications_enabled": False,
        },
        headers=auth_headers_system,
    )
    assert connect_response.status_code == 200
    connect_data = connect_response.json()
    assert connect_data["provider"] == "yandex"
    assert connect_data["settings"]["notifications_enabled"] is False

    reconnect_response = await frontend_client.post(
        "/frontend/api/calendar/integrations/connect",
        json={
            "provider": "yandex",
            "username": f"user-{unique_id}@yandex.ru",
            "access_token": "app-password-2",
            "refresh_token": None,
            "expires_at": None,
            "scope": None,
            "token_type": None,
            "default_calendar_id": "default",
            "sync_enabled": True,
            "sync_inbound_enabled": True,
            "sync_outbound_enabled": True,
            "notifications_enabled": True,
        },
        headers=auth_headers_system,
    )
    assert reconnect_response.status_code == 200
    reconnect_data = reconnect_response.json()
    assert reconnect_data["settings"]["notifications_enabled"] is True


@pytest.mark.asyncio
async def test_calendar_create_event_sends_invite_notification_by_attendee_id(
    unique_id: str,
    frontend_client,
    auth_headers_system,
    auth_token_system_user2,
    system_user2_id: str,
    monkeypatch,
) -> None:
    _ = auth_token_system_user2
    sent_notifications: list[tuple[str, object]] = []

    async def fake_notify_user(user_id: str, notification) -> None:
        sent_notifications.append((user_id, notification))

    monkeypatch.setattr("core.calendar.service.notify_user", fake_notify_user)

    start_at = datetime.now(timezone.utc) + timedelta(hours=1)
    end_at = start_at + timedelta(minutes=30)
    create_payload = {
        "title": f"Invite by attendee_id {unique_id}",
        "kind": "meeting",
        "source": "platform",
        "source_id": None,
        "namespace": "tests",
        "description": "Invite notification test",
        "location": "Room A",
        "status": "confirmed",
        "timezone": "UTC",
        "all_day": False,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "attendees": [{"attendee_id": system_user2_id}],
        "recurrence_rule": None,
        "recurrence_id": None,
        "series_id": None,
        "deep_link": None,
        "metadata": {},
    }
    create_response = await frontend_client.post(
        "/frontend/api/calendar/events",
        json=create_payload,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200
    created_event = create_response.json()
    event_id = created_event["event_id"]
    try:
        assert len(sent_notifications) == 1
        notified_user_id, notification = sent_notifications[0]
        assert notified_user_id == system_user2_id
        assert notification.type.value == "calendar_new_event"
        assert notification.service == "calendar"
        assert notification.data["event_id"] == event_id
    finally:
        await frontend_client.delete(
            f"/frontend/api/calendar/events/{event_id}",
            headers=auth_headers_system,
        )


@pytest.mark.asyncio
async def test_calendar_create_event_sends_invite_notification_by_attendee_email(
    unique_id: str,
    frontend_client,
    auth_headers_system,
    auth_token_system_user2,
    system_user2_id: str,
    monkeypatch,
) -> None:
    _ = auth_token_system_user2
    sent_notifications: list[tuple[str, object]] = []

    async def fake_notify_user(user_id: str, notification) -> None:
        sent_notifications.append((user_id, notification))

    monkeypatch.setattr("core.calendar.service.notify_user", fake_notify_user)

    attendee_email = f"{system_user2_id}@system.com"
    start_at = datetime.now(timezone.utc) + timedelta(hours=2)
    end_at = start_at + timedelta(minutes=45)
    create_payload = {
        "title": f"Invite by attendee_email {unique_id}",
        "kind": "meeting",
        "source": "platform",
        "source_id": None,
        "namespace": "tests",
        "description": "Invite notification by email",
        "location": "Room B",
        "status": "confirmed",
        "timezone": "UTC",
        "all_day": False,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "attendees": [{"email": attendee_email}],
        "recurrence_rule": None,
        "recurrence_id": None,
        "series_id": None,
        "deep_link": None,
        "metadata": {},
    }
    create_response = await frontend_client.post(
        "/frontend/api/calendar/events",
        json=create_payload,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200
    created_event = create_response.json()
    event_id = created_event["event_id"]
    try:
        assert len(sent_notifications) == 1
        notified_user_id, notification = sent_notifications[0]
        assert notified_user_id == system_user2_id
        assert notification.type.value == "calendar_new_event"
        assert notification.service == "calendar"
        assert notification.data["event_id"] == event_id
    finally:
        await frontend_client.delete(
            f"/frontend/api/calendar/events/{event_id}",
            headers=auth_headers_system,
        )
