"""E2E-сценарии «открываешь чат — история на месте, скролл вверх работает».

Все запросы идут к реальному `sync_service` (uvicorn 127.0.0.1:9005). Между
отправкой и чтением создаём НОВЫЙ `httpx.AsyncClient` — это имитирует
перезагрузку UI/F5: cookies/токен сохраняются, но соединение свежее.
"""

from __future__ import annotations

import pytest

from core.utils.tokens import get_token_service
from tests.sync.api._helpers import create_topic_channel_via_http
from tests.sync.api._realtime_helpers import (
    add_member_via_http,
    http_owner,
    send_text_message,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_history_visible_in_fresh_http_client_after_send(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """Owner шлёт 3 сообщения через одного клиента, второй (новый) клиент видит их."""
    async with http_owner(sync_auth_token) as http_send:
        channel_id = await create_topic_channel_via_http(
            http_send, http_send.headers,
            company_id=company_id, unique_id=unique_id, suffix="hist1",
            channel_name="hist1_ch",
        )
        sent_ids: list[str] = []
        for i in range(3):
            sent = await send_text_message(
                http_send, http_send.headers,
                channel_id=channel_id, text=f"msg{i:02d} {unique_id}",
            )
            sent_ids.append(sent["id"])

    async with http_owner(sync_auth_token) as http_read:
        r = await http_read.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [m["id"] for m in items] == sent_ids
    bodies = [
        next(c["data"]["body"] for c in m["contents"] if c["type"] == "text/plain")
        for m in items
    ]
    assert bodies == [f"msg{i:02d} {unique_id}" for i in range(3)]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_history_visible_for_other_member_in_fresh_http_client(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """User2 заходит в канал «впервые» (новый HTTP-клиент) и видит ленту."""
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="hist2",
            channel_name="hist2_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        for i in range(5):
            await send_text_message(
                http, http.headers,
                channel_id=channel_id, text=f"o{i} {unique_id}",
            )

    async with http_owner(sync_auth_token_user2) as http_user2:
        r = await http_user2.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 5
    bodies = [
        next(c["data"]["body"] for c in m["contents"] if c["type"] == "text/plain")
        for m in items
    ]
    assert bodies == [f"o{i} {unique_id}" for i in range(5)]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_history_pagination_loads_older_messages_with_before(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """30 сообщений: первая страница — 20 самых свежих + cursor, вторая — 10 старших."""
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="page",
            channel_name="page_ch",
        )
        for i in range(30):
            await send_text_message(
                http, http.headers,
                channel_id=channel_id, text=f"m{i:02d}",
            )

    async with http_owner(sync_auth_token) as http_read:
        page1 = await http_read.get(
            f"/sync/api/v1/channels/{channel_id}/messages?limit=20"
        )
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["items"]) == 20
        assert isinstance(body1["next_cursor"], str) and body1["next_cursor"] != ""
        first_text = next(c for c in body1["items"][0]["contents"] if c["type"] == "text/plain")
        last_text = next(c for c in body1["items"][-1]["contents"] if c["type"] == "text/plain")
        assert first_text["data"]["body"] == "m10"
        assert last_text["data"]["body"] == "m29"

        page2 = await http_read.get(
            f"/sync/api/v1/channels/{channel_id}/messages?before={body1['next_cursor']}&limit=20"
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert len(body2["items"]) == 10
        assert body2["next_cursor"] is None
        first2 = next(c for c in body2["items"][0]["contents"] if c["type"] == "text/plain")
        last2 = next(c for c in body2["items"][-1]["contents"] if c["type"] == "text/plain")
        assert first2["data"]["body"] == "m00"
        assert last2["data"]["body"] == "m09"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_history_excludes_deleted_messages(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="del",
            channel_name="del_history",
        )
        m1 = (await send_text_message(http, http.headers, channel_id=channel_id, text=f"keep1 {unique_id}"))["id"]
        m2 = (await send_text_message(http, http.headers, channel_id=channel_id, text=f"to-delete {unique_id}"))["id"]
        m3 = (await send_text_message(http, http.headers, channel_id=channel_id, text=f"keep2 {unique_id}"))["id"]
        r = await http.delete(f"/sync/api/v1/channels/{channel_id}/messages/{m2}")
        assert r.status_code == 200, r.text

    async with http_owner(sync_auth_token) as http_read:
        r = await http_read.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [m["id"] for m in items]
    assert ids == [m1, m3]
    assert m2 not in ids


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(60)
async def test_history_reflects_edits_and_reactions(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    """После edit и react в GET ленте — новый текст и реакции."""
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="edreact",
            channel_name="edreact_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        sent = await send_text_message(http, http.headers, channel_id=channel_id, text=f"v1 {unique_id}")
        message_id = sent["id"]
        e = await http.patch(
            f"/sync/api/v1/channels/{channel_id}/messages/{message_id}",
            json={
                "contents": [
                    {"type": "text/plain", "order": 0, "data": {"body": f"v2 {unique_id}"}},
                ]
            },
        )
        assert e.status_code == 200, e.text

    async with http_owner(sync_auth_token_user2) as http2:
        rr = await http2.post(
            f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/react",
            json={"emoji": "🔥"},
        )
        assert rr.status_code == 200, rr.text

    async with http_owner(sync_auth_token) as http_read:
        r = await http_read.get(f"/sync/api/v1/channels/{channel_id}/messages")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    msg = items[0]
    assert msg["id"] == message_id
    assert msg.get("edited_at") is not None
    text_block = next(c for c in msg["contents"] if c["type"] == "text/plain")
    assert text_block["data"]["body"] == f"v2 {unique_id}"
    emojis = [r.get("emoji") for r in msg.get("reactions", [])]
    assert "🔥" in emojis
