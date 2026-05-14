"""WebSocket: broadcast message.created нескольким клиентам."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.timeout(120)
async def test_two_ws_clients_receive_message_created(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_auth_token_user2,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    import websockets
    from httpx import AsyncClient

    from core.utils.tokens import get_token_service
    from tests.sync.api._helpers import seed_namespace_via_repo

    namespace = f"ns_{unique_id}_wsb"
    await seed_namespace_via_repo(company_id, namespace)
    async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=60.0) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            headers={"Authorization": f"Bearer {sync_auth_token}"},
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "ws_broadcast_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201
        channel_id = cr.json()["id"]

        token_service = get_token_service()
        u2_data = token_service.validate_token(sync_auth_token_user2)
        if u2_data is None:
            raise ValueError("Невалидный токен user2")
        u2_id = u2_data.user_id

        mr = await http.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            headers={"Authorization": f"Bearer {sync_auth_token}"},
            json={"user_id": u2_id, "role": "member"},
        )
        assert mr.status_code in (200, 201)

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"

    async def _wait_message_created(ws, expect_channel_id: str) -> dict:
        for _ in range(80):
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            parsed = json.loads(raw)
            if parsed.get("type") != "sync/message/created":
                continue
            payload = parsed.get("payload")
            if isinstance(payload, dict) and payload.get("channel_id") == expect_channel_id:
                return parsed
        raise AssertionError("Не получен sync/message/created для канала")

    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws1:
        async with websockets.connect(
            uri,
            additional_headers=[("Cookie", f"auth_token={sync_auth_token_user2}")],
        ) as ws2:
            t1 = asyncio.create_task(_wait_message_created(ws1, channel_id))
            t2 = asyncio.create_task(_wait_message_created(ws2, channel_id))
            await asyncio.sleep(0.25)

            async with AsyncClient(base_url="http://127.0.0.1:9005", timeout=60.0) as http_post:
                tr = await http_post.post(
                    f"/sync/api/v1/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bearer {sync_auth_token}"},
                    json={
                        "thread_id": None,
                        "parent_message_id": None,
                        "contents": [
                            {
                                "type": "text/plain",
                                "order": 0,
                                "data": {"body": f"broadcast ping {uuid.uuid4().hex[:8]}"},
                            },
                        ],
                    },
                )
                assert tr.status_code == 201

            got1, got2 = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=45.0)

    assert got1["type"] == "sync/message/created"
    assert got2["type"] == "sync/message/created"
