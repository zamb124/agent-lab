"""
Платформенная встреча (kind=meeting): канал Sync и ссылка через frontend ASGI и реальный Sync HTTP (порт 9005).

ServiceClient ходит на SERVER__SYNC_SERVICE_URL; sync_service поднимает процесс на 9005.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

import core.config.base as config_base


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_platform_calendar_sync_meeting_creates_sync_link_and_delete_removes_it(
    unique_id: str,
    frontend_client,
    sync_service,
    auth_headers_system,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SERVER__PLATFORM_PUBLIC_BASE_URL", "http://127.0.0.1:9004")
    config_base._settings_instance = None

    start_at = datetime.now(timezone.utc) + timedelta(hours=6)
    end_at = start_at + timedelta(hours=1)
    create_payload = {
        "title": f"Sync meeting {unique_id}",
        "kind": "meeting",
        "source": "platform",
        "source_id": None,
        "namespace": "tests",
        "description": None,
        "location": None,
        "status": "confirmed",
        "timezone": "UTC",
        "all_day": False,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "attendees": [],
        "recurrence_rule": None,
        "recurrence_id": None,
        "series_id": None,
        "deep_link": None,
        "metadata": {"case": f"sync_int_{unique_id}"},
    }
    create_response = await frontend_client.post(
        "/frontend/api/calendar/events",
        json=create_payload,
        headers=auth_headers_system,
    )
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    event_id = created["event_id"]
    metadata = created.get("metadata") or {}
    token = metadata.get("sync_link_token")
    assert token is not None and token != ""
    assert metadata.get("sync_meeting") == "1"
    deep_link = created.get("deep_link")
    assert isinstance(deep_link, str) and "/sync/join/" in deep_link

    try:
        async with AsyncClient(timeout=30.0) as http:
            join_resp = await http.get(f"http://127.0.0.1:9005/sync/api/v1/calls/join/{token}")
            assert join_resp.status_code == 200
            join_data = join_resp.json()
            assert join_data.get("link_token") == token

        update_payload = {
            **create_payload,
            "title": f"Sync meeting updated {unique_id}",
            "kind": "event",
        }
        update_response = await frontend_client.put(
            f"/frontend/api/calendar/events/{event_id}",
            json=update_payload,
            headers=auth_headers_system,
        )
        assert update_response.status_code == 200, update_response.text
        updated = update_response.json()
        updated_meta = updated.get("metadata") or {}
        assert updated_meta.get("sync_link_token") in (None, "")
        assert updated_meta.get("sync_meeting") not in ("1", 1)

        async with AsyncClient(timeout=30.0) as http:
            after_off = await http.get(f"http://127.0.0.1:9005/sync/api/v1/calls/join/{token}")
            assert after_off.status_code == 404
    finally:
        delete_response = await frontend_client.delete(
            f"/frontend/api/calendar/events/{event_id}",
            headers=auth_headers_system,
        )
        assert delete_response.status_code == 200
