"""WebSocket Sync: реальный сервер, Redis, sync worker — без моков auth/redis."""

from __future__ import annotations

import json
import uuid

import pytest


@pytest.mark.asyncio
async def test_ws_spaces_create_via_taskiq(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/ws"
    cmd_id = uuid.uuid4().hex
    frame = {
        "id": cmd_id,
        "type": "spaces.create",
        "payload": {"body": {"name": "WsSpace", "description": None}},
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(frame))
        data = None
        for _ in range(20):
            raw = await ws.recv()
            parsed = json.loads(raw)
            if parsed.get("id") == cmd_id and "ok" in parsed:
                data = parsed
                break
        assert data is not None, "ожидался WsResultFrame с id команды (возможен лишний broadcast)"
        assert data["ok"] is True
        assert data["result"]["name"] == "WsSpace"


@pytest.mark.asyncio
async def test_ws_rejects_without_auth_cookie(
    sync_service,
    sync_worker,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/ws"
    with pytest.raises(websockets.exceptions.InvalidStatus) as excinfo:
        async with websockets.connect(uri):
            pass
    assert excinfo.value.response.status_code == 403


@pytest.mark.asyncio
async def test_ws_task_error_frame(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/ws"
    cmd_id = uuid.uuid4().hex
    frame = {
        "id": cmd_id,
        "type": "spaces.update",
        "payload": {"space_id": "missing_space_ws", "body": {"name": "X"}},
    }
    async with websockets.connect(
        uri,
        additional_headers=[("Cookie", f"auth_token={sync_auth_token}")],
    ) as ws:
        await ws.send(json.dumps(frame))
        data = None
        for _ in range(20):
            raw = await ws.recv()
            parsed = json.loads(raw)
            if parsed.get("id") == cmd_id and "ok" in parsed:
                data = parsed
                break
        assert data is not None
        assert data["ok"] is False


@pytest.mark.asyncio
async def test_ws_two_commands_sequential(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
) -> None:
    import websockets

    uri = "ws://127.0.0.1:9005/sync/ws"
    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    f1 = {"id": id1, "type": "spaces.create", "payload": {"body": {"name": "WsA", "description": None}}}
    f2 = {"id": id2, "type": "spaces.create", "payload": {"body": {"name": "WsB", "description": None}}}
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
            cid = parsed.get("id")
            if cid in (id1, id2) and "ok" in parsed:
                got[cid] = parsed
            if len(got) == 2:
                break
        assert got[id1]["ok"] is True and got[id1]["result"]["name"] == "WsA"
        assert got[id2]["ok"] is True and got[id2]["result"]["name"] == "WsB"
