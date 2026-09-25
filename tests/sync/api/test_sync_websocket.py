"""User WS Sync через Centrifugo: кадр PlatformEvent, RPC platform.event."""

from __future__ import annotations

import uuid

import pytest
import websockets

from tests.realtime.centrifugo_ws import CENTRIFUGO_WS_URL, connect_centrifugo, wait_platform_event
from tests.sync.api._helpers import seed_namespace_via_repo
from tests.sync.api._realtime_helpers import send_ws_command
from tests.sync.conftest import require_sync_di


@pytest.mark.asyncio
async def test_ws_channels_create_via_command_router(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    namespace = f"ns_{unique_id}_ws"
    await seed_namespace_via_repo(require_sync_di(), company_id, namespace)

    event_id = uuid.uuid4().hex
    async with connect_centrifugo(sync_auth_token) as ws:
        await send_ws_command(
            ws,
            token=sync_auth_token,
            event_type="sync/channels/create_requested",
            payload={
                "type": "topic",
                "name": "WsTopic",
                "namespace": namespace,
                "is_private": False,
            },
            event_id=event_id,
        )
        reply = await wait_platform_event(ws, type_="sync/channels/create_succeeded")
        payload = reply.get("payload")
        assert isinstance(payload, dict)
        assert payload["name"] == "WsTopic"
        assert payload["namespace"] == namespace
        meta = reply.get("meta")
        assert isinstance(meta, dict)
        assert meta.get("causation_id") == event_id


@pytest.mark.asyncio
async def test_ws_rejects_without_auth_cookie(
    sync_service,
    sync_worker,
    sync_db_clean: None,
) -> None:
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as closed:
        async with websockets.connect(CENTRIFUGO_WS_URL) as connection:
            await connection.send('{"id":1,"connect":{}}')
            _ = await connection.recv()
    received = closed.value.rcvd
    if received is None:
        raise AssertionError("Centrifugo close frame is required")
    assert received.code == 3501


@pytest.mark.asyncio
async def test_ws_command_failed_when_target_missing(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
) -> None:
    event_id = uuid.uuid4().hex
    async with connect_centrifugo(sync_auth_token) as ws:
        await send_ws_command(
            ws,
            token=sync_auth_token,
            event_type="sync/channels/update_requested",
            payload={"channel_id": "missing_channel_ws", "body": {"name": "X"}},
            event_id=event_id,
        )
        reply = await wait_platform_event(ws, type_="sync/channels/update_failed")
        payload = reply.get("payload")
        assert isinstance(payload, dict)
        assert "error_code" in payload


@pytest.mark.asyncio
async def test_ws_two_commands_sequential(
    sync_service,
    sync_worker,
    sync_auth_token,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    namespace = f"ns_{unique_id}_seq"
    await seed_namespace_via_repo(require_sync_di(), company_id, namespace)

    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    async with connect_centrifugo(sync_auth_token) as ws:
        await send_ws_command(
            ws,
            token=sync_auth_token,
            event_type="sync/channels/create_requested",
            payload={
                "type": "topic",
                "name": "WsA",
                "namespace": namespace,
                "is_private": False,
            },
            event_id=id1,
        )
        await send_ws_command(
            ws,
            token=sync_auth_token,
            event_type="sync/channels/create_requested",
            payload={
                "type": "topic",
                "name": "WsB",
                "namespace": namespace,
                "is_private": False,
            },
            event_id=id2,
        )
        got: dict[str, dict[str, object]] = {}
        while len(got) < 2:
            event = await wait_platform_event(ws, type_="sync/channels/create_succeeded")
            meta = event.get("meta")
            if not isinstance(meta, dict):
                continue
            causation = meta.get("causation_id")
            if causation in (id1, id2):
                got[str(causation)] = event
        payload1 = got[id1].get("payload")
        assert isinstance(payload1, dict)
        assert payload1.get("name") == "WsA"
        payload2 = got[id2].get("payload")
        assert isinstance(payload2, dict)
        assert payload2.get("name") == "WsB"
