"""Матрица HTTP Sync: 401, 403, 404 и успешные вызовы по роутерам."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_http_spaces_unauthorized(sync_client, sync_db_clean: None) -> None:
    r = await sync_client.get("/sync/api/v1/spaces/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_http_channels_unauthorized(sync_client, sync_db_clean: None) -> None:
    r = await sync_client.get("/sync/api/v1/channels/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_http_messages_unauthorized(sync_client, sync_db_clean: None) -> None:
    r = await sync_client.get("/sync/api/v1/channels/ch1/messages")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_http_patch_space_not_found(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    with pytest.raises(ValueError, match="не найдено"):
        await sync_client.patch(
            "/sync/api/v1/spaces/nonexistent_space_id",
            headers=auth_headers_system,
            json={"name": "X"},
        )


@pytest.mark.asyncio
async def test_http_channel_members_404(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/channels/00000000000000000000000000000000/members",
        headers=auth_headers_system,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_channel_members_403_not_member(
    sync_client,
    auth_headers_system,
    auth_headers_system_user2,
    sync_db_clean: None,
) -> None:
    pr = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=auth_headers_system,
        json={"name": "M", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    cr = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=auth_headers_system,
        json={
            "space_id": space_id,
            "type": "topic",
            "name": "general",
            "is_private": False,
        },
    )
    assert cr.status_code == 201
    channel_id = cr.json()["id"]
    r = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=auth_headers_system_user2,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_http_company_members_ok(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get("/sync/api/v1/company/members", headers=auth_headers_system)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_http_git_resource_not_found(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/git/resources/gitlab:repo:x:no_such",
        headers=auth_headers_system,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_thread_not_found(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/threads/00000000000000000000000000000000",
        headers=auth_headers_system,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_list_threads_and_messages(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    pr = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=auth_headers_system,
        json={"name": "T", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    cr = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=auth_headers_system,
        json={
            "space_id": space_id,
            "type": "topic",
            "name": "chan",
            "is_private": False,
        },
    )
    assert cr.status_code == 201
    channel_id = cr.json()["id"]
    tr = await sync_client.get(
        f"/sync/api/v1/threads/?channel_id={channel_id}",
        headers=auth_headers_system,
    )
    assert tr.status_code == 200
    assert tr.json() == []
    mr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=auth_headers_system,
    )
    assert mr.status_code == 200
    assert mr.json() == []


@pytest.mark.asyncio
async def test_http_send_message_and_mark_read_flow(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    pr = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=auth_headers_system,
        json={"name": "Msg", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    cr = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=auth_headers_system,
        json={
            "space_id": space_id,
            "type": "topic",
            "name": "c",
            "is_private": False,
        },
    )
    assert cr.status_code == 201
    channel_id = cr.json()["id"]
    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=auth_headers_system,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {"type": "text/plain", "data": {"body": "hello"}, "order": 0},
            ],
        },
    )
    assert sr.status_code == 201
    mid = sr.json()["id"]
    rr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/read",
        headers=auth_headers_system,
    )
    assert rr.status_code == 204
    lr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=auth_headers_system,
    )
    assert lr.status_code == 200
    assert len(lr.json()) == 1
    assert lr.json()[0]["id"] == mid


@pytest.mark.asyncio
async def test_http_git_upsert(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    body = {
        "provider": "gitlab",
        "kind": "repo",
        "project_key": "pk",
        "external_id": "ext_http",
        "url": "https://gitlab.example/p",
        "extra": {},
    }
    r = await sync_client.post(
        "/sync/api/v1/git/resources",
        headers=auth_headers_system,
        json=body,
    )
    assert r.status_code == 201
    gid = r.json()["id"]
    gr = await sync_client.get(
        f"/sync/api/v1/git/resources/{gid}",
        headers=auth_headers_system,
    )
    assert gr.status_code == 200
    assert gr.json()["external_id"] == "ext_http"
