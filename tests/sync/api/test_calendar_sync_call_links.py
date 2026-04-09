"""
Создание календарных ссылок Sync и список scheduled (GET /calls/links/scheduled).

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
    sync_auth_headers,
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
        "call_type": "video",
    }
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
        json=body,
    )
    assert create.status_code == 201, create.text
    created = create.json()
    token = created["link_token"]
    assert created["calendar_event_id"] == event_id
    assert "/l/" in created["join_url"]
    assert created["join_url"].startswith("http://testserver/l/")

    dup = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
        json=body,
    )
    assert dup.status_code == 409

    info = await sync_client.get(f"/sync/api/v1/calls/join/{token}")
    assert info.status_code == 200
    assert info.json()["link_token"] == token

    scheduled_list = await sync_client.get(
        "/sync/api/v1/calls/links/scheduled",
        headers=sync_auth_headers,
        params={
            "start_at": (start - timedelta(hours=1)).isoformat(),
            "end_at": (end + timedelta(hours=1)).isoformat(),
        },
    )
    assert scheduled_list.status_code == 200
    scheduled_payload = scheduled_list.json()
    row = next((r for r in scheduled_payload if r.get("calendar_event_id") == event_id), None)
    assert row is not None
    assert row["link_token"] == token
    assert row["join_url"] is not None


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_patch_updates_window(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_patch_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=3)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
        json={
            "calendar_event_id": event_id,
            "scheduled_title": f"Before {unique_id}",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "calendar_member_user_ids": [],
        },
    )
    assert create.status_code == 201
    token = create.json()["link_token"]

    new_start = start + timedelta(hours=2)
    new_end = new_start + timedelta(hours=2)
    patch = await sync_client.patch(
        f"/sync/api/v1/calls/links/{token}",
        headers=sync_auth_headers,
        json={
            "scheduled_title": f"After {unique_id}",
            "scheduled_start_at": new_start.isoformat(),
            "scheduled_end_at": new_end.isoformat(),
        },
    )
    assert patch.status_code == 200
    patched = patch.json()
    assert patched["title"] == f"After {unique_id}"
    assert patched["join_url"].startswith("http://testserver/l/")


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_delete_removes_join_and_channel(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_del_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=4)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
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
        headers=sync_auth_headers,
    )
    assert delete.status_code == 204

    gone = await sync_client.get(f"/sync/api/v1/calls/join/{token}")
    assert gone.status_code == 404

    listed = await sync_client.get("/sync/api/v1/channels/", headers=sync_auth_headers)
    assert listed.status_code == 200
    channel_ids = {item["id"] for item in listed.json()}
    assert channel_id not in channel_ids


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_call_link_patch_syncs_channel_members(
    sync_client,
    sync_auth_headers,
    sync_user2_id: str,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_mem_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=6)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
        json={
            "calendar_event_id": event_id,
            "scheduled_title": f"Members {unique_id}",
            "scheduled_start_at": start.isoformat(),
            "scheduled_end_at": end.isoformat(),
            "calendar_member_user_ids": [],
        },
    )
    assert create.status_code == 201, create.text
    token = create.json()["link_token"]
    channel_id = create.json()["channel_id"]

    mem0 = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=sync_auth_headers,
    )
    assert mem0.status_code == 200
    ids0 = {row["user_id"] for row in mem0.json()}
    assert len(ids0) == 1

    patch_add = await sync_client.patch(
        f"/sync/api/v1/calls/links/{token}",
        headers=sync_auth_headers,
        json={"calendar_member_user_ids": [sync_user2_id]},
    )
    assert patch_add.status_code == 200, patch_add.text
    mem1 = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=sync_auth_headers,
    )
    assert mem1.status_code == 200
    ids1 = {row["user_id"] for row in mem1.json()}
    assert sync_user2_id in ids1
    assert len(ids1) == 2

    patch_clear = await sync_client.patch(
        f"/sync/api/v1/calls/links/{token}",
        headers=sync_auth_headers,
        json={"calendar_member_user_ids": []},
    )
    assert patch_clear.status_code == 200, patch_clear.text
    mem2 = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=sync_auth_headers,
    )
    assert mem2.status_code == 200
    ids2 = {row["user_id"] for row in mem2.json()}
    assert sync_user2_id not in ids2
    assert len(ids2) == 1


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_calendar_channel_type_is_calendar_meeting(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    event_id = f"cal_ch_{unique_id}"
    start = datetime.now(UTC) + timedelta(days=5)
    end = start + timedelta(hours=1)
    create = await sync_client.post(
        "/sync/api/v1/calls/links",
        headers=sync_auth_headers,
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

    listed = await sync_client.get("/sync/api/v1/channels/", headers=sync_auth_headers)
    assert listed.status_code == 200
    row = next((c for c in listed.json() if c["id"] == channel_id), None)
    assert row is not None
    assert row["type"] == CHANNEL_TYPE_CALENDAR_MEETING
