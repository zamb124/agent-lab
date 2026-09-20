"""E2E smoke: реальный HTTP worktracker_service на порту 9021."""

from __future__ import annotations

import pytest

from tests.worktracker.helpers.assertions import assert_items_object
from tests.worktracker.helpers.builders import build_manual_work_item_payload, build_queue_payload

pytestmark = pytest.mark.asyncio

PREFIX = "/worktracker/api/v1"


async def test_http_list_work_items(
    worktracker_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    create = await worktracker_client_http.post(
        f"{PREFIX}/work-items",
        headers=auth_headers_system,
        json=build_manual_work_item_payload(unique_id),
    )
    assert create.status_code == 201

    response = await worktracker_client_http.get(
        f"{PREFIX}/work-items",
        headers=auth_headers_system,
        params={"limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_http_mine_summary(
    worktracker_client_http,
    auth_headers_system,
) -> None:
    response = await worktracker_client_http.get(
        f"{PREFIX}/work-items/mine/summary",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_open_count"] >= 0
    assert body["queue_inbox_count"] >= 0


async def test_http_comments_items_object(
    worktracker_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    create = await worktracker_client_http.post(
        f"{PREFIX}/work-items",
        headers=auth_headers_system,
        json=build_manual_work_item_payload(unique_id),
    )
    assert create.status_code == 201
    work_item_id = create.json()["work_item_id"]
    comment = await worktracker_client_http.post(
        f"{PREFIX}/work-items/{work_item_id}/comments",
        headers=auth_headers_system,
        json={"text": f"note {unique_id}"},
    )
    assert comment.status_code == 201
    listed = await worktracker_client_http.get(
        f"{PREFIX}/work-items/{work_item_id}/comments",
        headers=auth_headers_system,
    )
    assert listed.status_code == 200
    comments = assert_items_object(listed.json())
    assert comments[0]["text"] == f"note {unique_id}"


async def test_http_queue_delete(
    worktracker_client_http,
    auth_headers_system,
    unique_id: str,
) -> None:
    created = await worktracker_client_http.post(
        f"{PREFIX}/work-queues",
        headers=auth_headers_system,
        json=build_queue_payload(unique_id),
    )
    assert created.status_code == 201
    queue_id = created.json()["work_queue_id"]
    deleted = await worktracker_client_http.delete(
        f"{PREFIX}/work-queues/{queue_id}",
        headers=auth_headers_system,
    )
    assert deleted.status_code == 204
    members = await worktracker_client_http.get(
        f"{PREFIX}/work-queues/{queue_id}/members",
        headers=auth_headers_system,
    )
    assert members.status_code == 403
