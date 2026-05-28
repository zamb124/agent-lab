"""WebSocket Sync: единый платформенный сокет /sync/api/ws/notifications.

Контракт фрейма (см. `architecture.mdc`, раздел «REST-зеркало команд»):

  client -> server:  { request_id, type: 'sync/<entity>/<verb>_requested', payload }
  server -> client:  { request_id, type: 'sync/<entity>/<verb>_succeeded'|'..._failed', payload }
                     либо push без request_id: { type, payload, meta? } из platform:ui_events.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.sync.api._helpers import seed_namespace_via_repo


@pytest.mark.asyncio
async def test_ws_channels_create_via_command_router(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    import websockets

    namespace = f"ns_{unique_id}_ws"
    await seed_namespace_via_repo(company_id, namespace)

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    request_id = uuid.uuid4().hex
    frame = {
        "request_id": request_id,
        "type": "sync/channels/create_requested",
        "payload": {
            "type": "topic",
            "name": "WsTopic",
            "namespace": namespace,
            "is_private": False,
        },
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(frame))
        reply = None
        for _ in range(20):
            raw = await ws.recv()
            parsed = json.loads(raw)
            if parsed.get("request_id") == request_id:
                reply = parsed
                break
        assert reply is not None, "ожидался reply-фрейм с тем же request_id"
        assert reply["type"] == "sync/channels/create_succeeded"
        assert reply["payload"]["name"] == "WsTopic"
        assert reply["payload"]["namespace"] == namespace


@pytest.mark.asyncio
async def test_ws_rejects_without_auth_cookie(
    sync_service,
    sync_worker,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    with pytest.raises((websockets.exceptions.InvalidStatus, websockets.exceptions.ConnectionClosed)):
        async with websockets.connect(uri) as ws:
            await ws.recv()


@pytest.mark.asyncio
async def test_ws_command_failed_when_target_missing(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    request_id = uuid.uuid4().hex
    frame = {
        "request_id": request_id,
        "type": "sync/channels/update_requested",
        "payload": {"channel_id": "missing_channel_ws", "body": {"name": "X"}},
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(frame))
        reply = None
        for _ in range(20):
            raw = await ws.recv()
            parsed = json.loads(raw)
            if parsed.get("request_id") == request_id:
                reply = parsed
                break
        assert reply is not None
        assert reply["type"] == "sync/channels/update_failed"
        assert "error_code" in reply["payload"]


@pytest.mark.asyncio
async def test_ws_two_commands_sequential(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    import websockets

    namespace = f"ns_{unique_id}_seq"
    await seed_namespace_via_repo(company_id, namespace)

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    f1 = {
        "request_id": id1,
        "type": "sync/channels/create_requested",
        "payload": {
            "type": "topic",
            "name": "WsA",
            "namespace": namespace,
            "is_private": False,
        },
    }
    f2 = {
        "request_id": id2,
        "type": "sync/channels/create_requested",
        "payload": {
            "type": "topic",
            "name": "WsB",
            "namespace": namespace,
            "is_private": False,
        },
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(f1))
        await ws.send(json.dumps(f2))
        got: dict[str, dict[str, object]] = {}
        for _ in range(40):
            raw = await ws.recv()
            parsed = json.loads(raw)
            rid = parsed.get("request_id")
            if rid in (id1, id2):
                got[rid] = parsed
            if len(got) == 2:
                break
        reply1 = got[id1]
        payload1 = reply1.get("payload")
        assert isinstance(payload1, dict)
        assert reply1.get("type") == "sync/channels/create_succeeded"
        assert payload1.get("name") == "WsA"
        reply2 = got[id2]
        payload2 = reply2.get("payload")
        assert isinstance(payload2, dict)
        assert reply2.get("type") == "sync/channels/create_succeeded"
        assert payload2.get("name") == "WsB"
