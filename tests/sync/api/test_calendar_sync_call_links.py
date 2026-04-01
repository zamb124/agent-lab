"""
Создание календарных ссылок Sync, список scheduled, детали synthetic meeting_id.

Реальный sync ASGI, PostgreSQL, без моков внутренних компонентов.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.sync.constants import CHANNEL_TYPE_CALENDAR_MEETING


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_create_list_meetings_scheduled_detail_and_duplicate(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_evt_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=2)
    end = start + timedelta(hours=1)
    body = {
        "calendar_event_id": event_id,
        "scheduled_title": f"Scheduled {unique_id}",
        "scheduled_start_at": start.isoformat(),
        "scheduled_end_at": end.isoformat(),
        "calendar_member_user_ids": [],
        "join_url_base": "https://app.test.example.com",
        "call_type": "video",
    }
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json=body,
    )
    assert create.status_code == 201, create.text
    created = create.json()
    token = created["link_token"]
    assert created["calendar_event_id"] == event_id
    assert "sync/join/" in created["join_url"]
    assert created["join_url"].startswith("https://app.test.example.com/sync/join/")

    dup = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json=body,
    )
    assert dup.status_code == 409

    info = await sync_client.get(f"/sync/api/v1/calls/join/{token}")
    assert info.status_code == 200
    assert info.json()["link_token"] == token

    scheduled_list = await sync_client.get(
        "/sync/api/v1/calls/links/scheduled",
        headers=auth_headers_system,
        params={
            "start_at": (start - timedelta(hours=1)).isoformat(),
            "end_at": (end + timedelta(hours=1)).isoformat(),
        },
    )
    assert scheduled_list.status_code == 200
    scheduled_payload = scheduled_list.json()
    assert any(row.get("calendar_event_id") == event_id for row in scheduled_payload)

    meetings = await sync_client.get("/sync/api/v1/meetings/", headers=auth_headers_system)
    assert meetings.status_code == 200
    rows = meetings.json()
    synthetic = next((m for m in rows if m.get("meeting_id") == f"scheduled:{event_id}"), None)
    assert synthetic is not None
    assert synthetic["meeting_kind"] == "scheduled"
    assert synthetic["link_token"] == token
    assert synthetic["join_url"] is not None

    detail = await sync_client.get(
        f"/sync/api/v1/meetings/scheduled:{event_id}",
        headers=auth_headers_system,
    )
    assert detail.status_code == 200
    detail_meeting = detail.json()["meeting"]
    assert detail_meeting["meeting_kind"] == "scheduled"
    assert detail_meeting["link_token"] == token
    assert detail_meeting["calendar_event_id"] == event_id


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_patch_updates_window(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_patch_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=3)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={
            "calendar_event_id": event_id,
            "scheduled_title": f"Before {unique_id}",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "calendar_member_user_ids": [],
            "join_url_base": "https://app.test.example.com",
        },
    )
    assert create.status_code == 201
    token = create.json()["link_token"]

    new_start = start + timedelta(hours=2)
    new_end = new_start + timedelta(hours=2)
    patch = await sync_client.patch(
        f"/sync/api/v1/calls/links/{token}",
        headers=auth_headers_system,
        json={
            "scheduled_title": f"After {unique_id}",
            "scheduled_start_at": new_start.isoformat(),
            "scheduled_end_at": new_end.isoformat(),
            "join_url_base": "https://join.test.example.com",
        },
    )
    assert patch.status_code == 200
    patched = patch.json()
    assert patched["title"] == f"After {unique_id}"
    assert patched["join_url"].startswith("https://join.test.example.com/sync/join/")


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_delete_removes_join_and_channel(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_del_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=4)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={
            "calendar_event_id": event_id,
            "scheduled_title": f"Del {unique_id}",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "calendar_member_user_ids": [],
        },
    )
    assert create.status_code == 201
    token = create.json()["link_token"]
    channel_id = create.json()["channel_id"]

    delete = await sync_client.delete(
        f"/sync/api/v1/calls/links/{token}",
        headers=auth_headers_system,
    )
    assert delete.status_code == 204

    gone = await sync_client.get(f"/sync/api/v1/calls/join/{token}")
    assert gone.status_code == 404

    listed = await sync_client.get("/sync/api/v1/channels/", headers=auth_headers_system)
    assert listed.status_code == 200
    channel_ids = {item["id"] for item in listed.json()}
    assert channel_id not in channel_ids


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_channel_type_is_calendar_meeting(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_ch_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=5)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=auth_headers_system,
        json={
            "calendar_event_id": event_id,
            "scheduled_title": f"Ch {unique_id}",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "calendar_member_user_ids": [],
        },
    )
    assert create.status_code == 201
    channel_id = create.json()["channel_id"]

    listed = await sync_client.get("/sync/api/v1/channels/", headers=auth_headers_system)
    assert listed.status_code == 200
    row = next((c for c in listed.json() if c["id"] == channel_id), None)
    assert row is not None
    assert row["type"] == CHANNEL_TYPE_CALENDAR_MEETING
