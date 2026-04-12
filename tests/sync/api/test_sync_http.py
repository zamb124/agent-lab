"""Интеграционные тесты Sync HTTP API (ASGI, Bearer, реальный sync worker)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_http_list_spaces_empty(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get("/sync/api/v1/spaces/", headers=sync_auth_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_http_create_space_taskiq(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=sync_auth_headers,
        json={"name": "HttpSpace", "description": None},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "HttpSpace"


@pytest.mark.asyncio
async def test_http_patch_space_dispatch(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    pr = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=sync_auth_headers,
        json={"name": "ToPatch", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    r = await sync_client.patch(
        f"/sync/api/v1/spaces/{space_id}",
        headers=sync_auth_headers,
        json={"name": "Patched"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Patched"


@pytest.mark.asyncio
async def test_http_list_channels_empty(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get("/sync/api/v1/channels/", headers=sync_auth_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []
