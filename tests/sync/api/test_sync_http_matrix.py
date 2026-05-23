"""Матрица HTTP Sync: 401, 403, 404 и успешные вызовы по роутерам."""

from __future__ import annotations

import pytest

from tests.sync.api._helpers import create_topic_channel_via_http


@pytest.mark.asyncio
async def test_http_namespaces_unauthorized(sync_client, sync_db_clean: None) -> None:
    r = await sync_client.get("/sync/api/v1/namespaces")
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
async def test_http_put_namespace_not_found_returns_404(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.put(
        "/sync/api/v1/namespaces/nonexistent_ns",
        headers=sync_auth_headers,
        json={"sync_settings": None},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_channel_members_404(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/channels/00000000000000000000000000000000/members",
        headers=sync_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_channel_members_403_not_member(
    sync_client,
    sync_auth_headers,
    sync_auth_headers_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="m",
        channel_name="general",
    )
    r = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/members",
        headers=sync_auth_headers_user2,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_http_company_members_ok(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get("/sync/api/v1/company/members", headers=sync_auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["items"], list)
    for row in data["items"]:
        assert "is_online" in row
        assert isinstance(row["is_online"], bool)
        assert "last_seen_at" in row


@pytest.mark.asyncio
async def test_http_git_resource_not_found(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/git/resources/gitlab:repo:x:no_such",
        headers=sync_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_thread_not_found(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/threads/00000000000000000000000000000000",
        headers=sync_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_list_threads_and_messages(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="t",
        channel_name="chan",
    )
    tr = await sync_client.get(
        f"/sync/api/v1/threads/?channel_id={channel_id}",
        headers=sync_auth_headers,
    )
    assert tr.status_code == 200
    assert tr.json()["items"] == []
    mr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert mr.status_code == 200
    assert mr.json()["items"] == []


@pytest.mark.asyncio
async def test_http_send_message_and_mark_read_flow(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="msg",
        channel_name="c",
    )
    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {"type": "text/plain", "data": {"body": "hello"}, "order": 0},
            ],
        },
    )
    assert sr.status_code == 201
    mid = sr.json()["message_id"]
    rr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/read",
        headers=sync_auth_headers,
    )
    assert rr.status_code == 204
    lr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert lr.status_code == 200
    assert len(lr.json()["items"]) == 1
    assert lr.json()["items"][0]["message_id"] == mid


@pytest.mark.asyncio
async def test_http_git_upsert(
    sync_client,
    sync_auth_headers,
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
        headers=sync_auth_headers,
        json=body,
    )
    assert r.status_code == 201
    git_ref_id = r.json()["git_ref_id"]
    assert "id" not in r.json()
    gr = await sync_client.get(
        f"/sync/api/v1/git/resources/{git_ref_id}",
        headers=sync_auth_headers,
    )
    assert gr.status_code == 200
    assert gr.json()["git_ref_id"] == git_ref_id
    assert gr.json()["external_id"] == "ext_http"


@pytest.mark.asyncio
@pytest.mark.timeout(20)
async def test_http_messages_default_limit_and_cursor_pagination(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="pag",
        channel_name="paginated-channel",
    )

    for idx in range(25):
        sr = await sync_client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            headers=sync_auth_headers,
            json={
                "thread_id": None,
                "parent_message_id": None,
                "contents": [
                    {"type": "text/plain", "data": {"body": f"m{idx:02d}"}, "order": 0},
                ],
            },
        )
        assert sr.status_code == 201

    first_page = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert isinstance(payload["items"], list)
    assert len(payload["items"]) == 20
    assert isinstance(payload["next_cursor"], str)
    first_body = payload["items"][0]["contents"][0]["data"]["body"]
    last_body = payload["items"][-1]["contents"][0]["data"]["body"]
    assert first_body == "m05"
    assert last_body == "m24"

    second_page = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages?before={payload['next_cursor']}&limit=20",
        headers=sync_auth_headers,
    )
    assert second_page.status_code == 200
    payload2 = second_page.json()
    assert len(payload2["items"]) == 5
    assert payload2["next_cursor"] is None
    assert payload2["items"][0]["contents"][0]["data"]["body"] == "m00"
    assert payload2["items"][-1]["contents"][0]["data"]["body"] == "m04"


@pytest.mark.asyncio
async def test_http_messages_invalid_cursor_returns_400(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="badcur",
        channel_name="bad-cursor-channel",
    )

    response = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages?before=not_base64",
        headers=sync_auth_headers,
    )
    assert response.status_code == 400
