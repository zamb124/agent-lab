"""
Интеграционные тесты доступности календарного API во всех сервисах.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _calendar_list_payload() -> dict[str, str | int | list[str]]:
    now = datetime.now(timezone.utc)
    return {
        "start_at": (now - timedelta(days=14)).isoformat(),
        "end_at": (now + timedelta(days=30)).isoformat(),
        "include_sources": ["platform"],
        "limit": 2000,
    }


@pytest.mark.asyncio
async def test_calendar_list_endpoint_available_in_all_services(
    unique_id: str,
    frontend_client,
    flows_client,
    crm_client,
    rag_client,
    sync_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    clients = [
        ("frontend", frontend_client, "/frontend/api/calendar/events/list"),
        ("flows", flows_client, "/flows/api/calendar/events/list"),
        ("crm", crm_client, "/crm/api/calendar/events/list"),
        ("rag", rag_client, "/rag/api/calendar/events/list"),
        ("sync", sync_client, "/sync/api/calendar/events/list"),
    ]
    payload = _calendar_list_payload()

    for service_name, client, url in clients:
        response = await client.post(url, json=payload, headers=auth_headers_system)
        assert response.status_code == 200, f"{service_name} must expose calendar list endpoint"
        data = response.json()
        assert isinstance(data, dict)
        assert "events" in data and isinstance(data["events"], list)
        assert "integrations" in data and isinstance(data["integrations"], list)


@pytest.mark.asyncio
async def test_calendar_events_created_in_one_service_visible_in_all_services(
    unique_id: str,
    frontend_client,
    flows_client,
    crm_client,
    rag_client,
    sync_client,
    auth_headers_system,
) -> None:
    now = datetime.now(timezone.utc)
    create_payload = {
        "title": f"Cross service calendar event {unique_id}",
        "kind": "event",
        "source": "platform",
        "source_id": None,
        "namespace": None,
        "description": "Cross-service visibility check",
        "location": "online",
        "status": "confirmed",
        "timezone": "UTC",
        "all_day": False,
        "start_at": (now + timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(minutes=35)).isoformat(),
        "attendees": [],
        "recurrence_rule": None,
        "recurrence_id": None,
        "series_id": None,
        "deep_link": None,
        "metadata": {"test_case": f"cross_service_{unique_id}"},
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
        clients = [
            ("frontend", frontend_client, "/frontend/api/calendar/events/list"),
            ("flows", flows_client, "/flows/api/calendar/events/list"),
            ("crm", crm_client, "/crm/api/calendar/events/list"),
            ("rag", rag_client, "/rag/api/calendar/events/list"),
            ("sync", sync_client, "/sync/api/calendar/events/list"),
        ]
        payload = _calendar_list_payload()

        for service_name, client, url in clients:
            response = await client.post(url, json=payload, headers=auth_headers_system)
            assert response.status_code == 200, f"{service_name} must return calendar list"
            events = response.json()["events"]
            event_ids = {item["event_id"] for item in events}
            assert event_id in event_ids, f"{service_name} must see event created through frontend"
    finally:
        await frontend_client.delete(
            f"/frontend/api/calendar/events/{event_id}",
            headers=auth_headers_system,
        )
