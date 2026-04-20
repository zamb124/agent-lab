"""E2E realtime-сценарии sync через настоящий WebSocket.

Все тесты идут через `sync_service` (uvicorn на 127.0.0.1:9005) и
`sync_worker` (TaskIQ); никаких моков, monkeypatch или подмен внутренностей.

Для каждого сценария:
  1. Создаём namespace + topic-канал.
  2. Подключаем (где надо) пользователей-участников через REST.
  3. Открываем по одному WebSocket на каждого подписчика, ждём готовности.
  4. Триггерим действие (REST) и ждём конкретный push-фрейм у каждого.

Контракт фреймов фиксируется тестами: при изменении формы payload или
канонического имени (`sync/<entity>/<verb>`) тесты падают, что и нужно.
"""

from __future__ import annotations

import asyncio

import pytest

from core.utils.tokens import get_token_service

from tests.sync.api._helpers import (
    create_topic_channel_via_http,
    seed_namespace_via_repo,
)
from tests.sync.api._realtime_helpers import (
    add_member_via_http,
    add_third_user,
    connect_ws,
    http_owner,
    send_text_message,
    wait_frame,
)


def _user_id_from_token(token: str) -> str:
    data = get_token_service().validate_token(token)
    if data is None:
        raise AssertionError("invalid token")
    return data.user_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_three_clients_message_created_broadcast(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    user3_id = f"sync_user3_{unique_id}"
    sync_auth_token_user3 = await add_third_user(company_id=company_id, user_id=user3_id)

    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http,
            http.headers,
            company_id=company_id,
            unique_id=unique_id,
            suffix="three",
            channel_name="three_clients",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user3_id)

    async with connect_ws(sync_auth_token) as ws_owner, \
            connect_ws(sync_auth_token_user2) as ws_user2, \
            connect_ws(sync_auth_token_user3) as ws_user3:
        await asyncio.sleep(0.3)

        async with http_owner(sync_auth_token) as http:
            sent = await send_text_message(
                http, http.headers,
                channel_id=channel_id,
                text=f"three-broadcast {unique_id}",
            )
        message_id = sent["id"]

        async def wait_for(ws):
            return await wait_frame(
                ws,
                type_="sync/message/created",
                where=lambda p: p.get("channel_id") == channel_id and p.get("id") == message_id,
                timeout=20.0,
            )

        owner_frame, user2_frame, user3_frame = await asyncio.gather(
            wait_for(ws_owner), wait_for(ws_user2), wait_for(ws_user3)
        )

    for frame in (owner_frame, user2_frame, user3_frame):
        assert frame["payload"]["id"] == message_id
        assert frame["payload"]["channel_id"] == channel_id
        text_block = next(c for c in frame["payload"]["contents"] if c["type"] == "text/plain")
        assert text_block["data"]["body"] == f"three-broadcast {unique_id}"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_message_reaction_changed_broadcast(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="react",
            channel_name="react_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        sent = await send_text_message(http, http.headers, channel_id=channel_id, text=f"hi {unique_id}")
    message_id = sent["id"]

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token_user2) as http2:
            r = await http2.post(
                f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/react",
                json={"emoji": "👍"},
            )
            assert r.status_code == 200, r.text

        frame = await wait_frame(
            ws_owner,
            type_="sync/message/reaction_changed",
            where=lambda p: p.get("message_id") == message_id and p.get("channel_id") == channel_id,
            timeout=15.0,
        )

    reactions = frame["payload"]["reactions"]
    assert isinstance(reactions, list) and len(reactions) >= 1
    emojis = [r.get("emoji") for r in reactions]
    assert "👍" in emojis


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_message_reply_propagates_parent_message_id(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="reply",
            channel_name="reply_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        root = await send_text_message(http, http.headers, channel_id=channel_id, text=f"root {unique_id}")
    root_id = root["id"]

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token_user2) as http2:
            reply = await send_text_message(
                http2, http2.headers,
                channel_id=channel_id,
                text=f"reply {unique_id}",
                parent_message_id=root_id,
            )
        reply_id = reply["id"]

        frame = await wait_frame(
            ws_owner,
            type_="sync/message/created",
            where=lambda p: p.get("id") == reply_id,
            timeout=15.0,
        )

    assert frame["payload"]["parent_message_id"] == root_id
    assert frame["payload"]["channel_id"] == channel_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_message_updated_broadcast_on_edit(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="edit",
            channel_name="edit_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        sent = await send_text_message(http, http.headers, channel_id=channel_id, text=f"v1 {unique_id}")
    message_id = sent["id"]

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.patch(
                f"/sync/api/v1/channels/{channel_id}/messages/{message_id}",
                json={
                    "contents": [
                        {"type": "text/plain", "order": 0, "data": {"body": f"v2 {unique_id}"}},
                    ]
                },
            )
            assert r.status_code == 200, r.text

        frame = await wait_frame(
            ws_user2,
            type_="sync/message/updated",
            where=lambda p: p.get("id") == message_id,
            timeout=15.0,
        )

    new_text = next(c for c in frame["payload"]["contents"] if c["type"] == "text/plain")
    assert new_text["data"]["body"] == f"v2 {unique_id}"
    assert frame["payload"].get("edited_at") is not None


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_message_deleted_broadcast(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="del",
            channel_name="del_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        sent = await send_text_message(http, http.headers, channel_id=channel_id, text=f"to-delete {unique_id}")
    message_id = sent["id"]

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.delete(f"/sync/api/v1/channels/{channel_id}/messages/{message_id}")
            assert r.status_code == 200, r.text

        frame = await wait_frame(
            ws_user2,
            type_="sync/message/deleted",
            where=lambda p: p.get("message_id") == message_id and p.get("channel_id") == channel_id,
            timeout=15.0,
        )

    assert frame["payload"]["message_id"] == message_id
    assert frame["payload"]["channel_id"] == channel_id


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_channel_read_updated_broadcast_on_mark_read(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="read",
            channel_name="read_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)
        await send_text_message(http, http.headers, channel_id=channel_id, text=f"trigger {unique_id}")

    async with connect_ws(sync_auth_token) as ws_owner:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token_user2) as http2:
            r = await http2.post(f"/sync/api/v1/channels/{channel_id}/read")
            assert r.status_code == 204, r.text

        frame = await wait_frame(
            ws_owner,
            type_="sync/channel/read_updated",
            where=lambda p: p.get("channel_id") == channel_id and p.get("reader_user_id") == user2_id,
            timeout=15.0,
        )

    assert isinstance(frame["payload"]["read_at"], str) and frame["payload"]["read_at"] != ""


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_forward_publishes_message_created_in_target_channel(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    user3_id = f"sync_user3_fwd_{unique_id}"
    sync_auth_token_user3 = await add_third_user(company_id=company_id, user_id=user3_id)

    async with http_owner(sync_auth_token) as http:
        ns_a = f"ns_{unique_id}_fwd_a"
        ns_b = f"ns_{unique_id}_fwd_b"
        await seed_namespace_via_repo(company_id, ns_a)
        await seed_namespace_via_repo(company_id, ns_b)

        cr_a = await http.post(
            "/sync/api/v1/channels/",
            json={"namespace": ns_a, "type": "topic", "name": "fwd_src", "is_private": False},
        )
        assert cr_a.status_code == 201
        channel_a = cr_a.json()["id"]
        cr_b = await http.post(
            "/sync/api/v1/channels/",
            json={"namespace": ns_b, "type": "topic", "name": "fwd_dst", "is_private": False},
        )
        assert cr_b.status_code == 201
        channel_b = cr_b.json()["id"]

        await add_member_via_http(http, http.headers, channel_id=channel_a, user_id=user2_id)
        await add_member_via_http(http, http.headers, channel_id=channel_b, user_id=user3_id)
        sent = await send_text_message(http, http.headers, channel_id=channel_a, text=f"to-fwd {unique_id}")
        message_id = sent["id"]

    async with connect_ws(sync_auth_token_user3) as ws_user3:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            r = await http.post(
                f"/sync/api/v1/channels/{channel_a}/messages/{message_id}/forward",
                json={"to_channel_id": channel_b},
            )
            assert r.status_code == 201, r.text
            forwarded_id = r.json()["id"]

        frame = await wait_frame(
            ws_user3,
            type_="sync/message/created",
            where=lambda p: p.get("channel_id") == channel_b and p.get("id") == forwarded_id,
            timeout=15.0,
        )

    forwarded_from = frame["payload"].get("forwarded_from")
    assert isinstance(forwarded_from, dict)
    assert forwarded_from.get("channel_id") == channel_a


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_mention_broadcast_includes_mentioned_user_ids(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    user2_id = _user_id_from_token(sync_auth_token_user2)
    async with http_owner(sync_auth_token) as http:
        channel_id = await create_topic_channel_via_http(
            http, http.headers,
            company_id=company_id, unique_id=unique_id, suffix="mention",
            channel_name="mention_ch",
        )
        await add_member_via_http(http, http.headers, channel_id=channel_id, user_id=user2_id)

    async with connect_ws(sync_auth_token_user2) as ws_user2:
        await asyncio.sleep(0.3)
        async with http_owner(sync_auth_token) as http:
            sent = await send_text_message(
                http, http.headers,
                channel_id=channel_id,
                text=f"hey @{user2_id} {unique_id}",
                mentioned_user_ids=[user2_id],
            )
        message_id = sent["id"]

        frame = await wait_frame(
            ws_user2,
            type_="sync/message/created",
            where=lambda p: p.get("id") == message_id,
            timeout=15.0,
        )

    mentioned = frame["payload"].get("mentioned_user_ids")
    assert isinstance(mentioned, list) and user2_id in mentioned
    text_block = next(c for c in frame["payload"]["contents"] if c["type"] == "text/plain")
    text_mentions = text_block["data"].get("mentions")
    assert isinstance(text_mentions, list) and user2_id in text_mentions
