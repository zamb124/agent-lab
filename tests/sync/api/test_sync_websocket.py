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


@pytest.mark.asyncio
async def test_ws_spaces_create_via_command_router(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    request_id = uuid.uuid4().hex
    frame = {
        "request_id": request_id,
        "type": "sync/spaces/create_requested",
        "payload": {
            "body": {
                "name": "WsSpace",
                "description": None,
                "namespace": f"ws_{unique_id}",
            }
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
        assert reply["type"] == "sync/spaces/create_succeeded"
        assert reply["payload"]["name"] == "WsSpace"


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
        "type": "sync/spaces/update_requested",
        "payload": {"space_id": "missing_space_ws", "body": {"name": "X"}},
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
        assert reply["type"] == "sync/spaces/update_failed"
        assert "error_code" in reply["payload"]


@pytest.mark.asyncio
async def test_ws_two_commands_sequential(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/api/ws/notifications"
    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    f1 = {
        "request_id": id1,
        "type": "sync/spaces/create_requested",
        "payload": {
            "body": {
                "name": "WsA",
                "description": None,
                "namespace": f"wsa_{unique_id}",
            }
        },
    }
    f2 = {
        "request_id": id2,
        "type": "sync/spaces/create_requested",
        "payload": {
            "body": {
                "name": "WsB",
                "description": None,
                "namespace": f"wsb_{unique_id}",
            }
        },
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(f1))
        await ws.send(json.dumps(f2))
        got: dict[str, dict] = {}
        for _ in range(40):
            raw = await ws.recv()
            parsed = json.loads(raw)
            rid = parsed.get("request_id")
            if rid in (id1, id2):
                got[rid] = parsed
            if len(got) == 2:
                break
        assert got[id1]["type"] == "sync/spaces/create_succeeded"
        assert got[id1]["payload"]["name"] == "WsA"
        assert got[id2]["type"] == "sync/spaces/create_succeeded"
        assert got[id2]["payload"]["name"] == "WsB"
