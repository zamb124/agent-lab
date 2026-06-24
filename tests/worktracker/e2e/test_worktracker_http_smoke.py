"""E2E smoke: реальный HTTP worktracker_service на порту 9021."""

from __future__ import annotations

import pytest

from tests.worktracker.helpers.builders import build_manual_work_item_payload

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
