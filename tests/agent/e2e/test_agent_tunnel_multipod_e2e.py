"""E2E multi-pod HumanitecAgent tunnel bus."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from httpx import AsyncClient

from apps.agent.tunnel_bus import (
    TUNNEL_MCP_REQUEST_CHANNEL,
    get_pod_instance_id,
    send_mcp_request_to_device,
)
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    FRONTEND_TUNNEL_POD_ID,
    PLATFORM_MCP_PATH,
    pair_and_register_device,
)
from tests.agent._realtime_helpers import (
    AGENT_TUNNEL_WS_PATH,
    FRONTEND_WS_BASE,
    connect_agent_tunnel_ws,
    wait_tunnel_json,
)


@pytest.mark.asyncio
async def test_e2e_multipod_mcp_full_roundtrip(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)

        async def responder() -> None:
            while True:
                raw = await websocket.recv()
                payload = json.loads(raw)
                if payload.get("type") != "mcp_request":
                    continue
                request_id = payload.get("request_id")
                await websocket.send(
                    json.dumps(
                        {
                            "type": "mcp_response",
                            "request_id": request_id,
                            "result": {"tools": [{"name": "bus-local"}]},
                        }
                    )
                )
                return

        responder_task = asyncio.create_task(responder())
        result = await send_mcp_request_to_device(
            frontend_container.redis_client,
            device_id,
            method="tools/list",
            params={},
            timeout_seconds=10.0,
        )
        await responder_task
        assert result == {"tools": [{"name": "bus-local"}]}


@pytest.mark.asyncio
async def test_e2e_multipod_revoke_disconnects_ws(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    ws_uri = f"{FRONTEND_WS_BASE}{AGENT_TUNNEL_WS_PATH}?token={device_token}"
    async with websockets.connect(ws_uri) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        revoke_response = await agent_frontend_http_client.delete(
            f"{AGENT_API_PREFIX}/devices/{device_id}",
            timeout=30.0,
        )
        assert revoke_response.status_code == 204
        await websocket.send(json.dumps({"type": "ping"}))
        with pytest.raises(
            (
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
            )
        ) as exc_info:
            await asyncio.wait_for(websocket.recv(), timeout=10.0)
        if isinstance(exc_info.value, websockets.exceptions.ConnectionClosedError):
            assert exc_info.value.code in {4401, 4403, 1000, 1006}


@pytest.mark.asyncio
async def test_e2e_multipod_origin_pod_skip(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    assert get_pod_instance_id() == f"pod-b-{unique_id}"

    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)

        received_request_ids: list[str] = []
        request_received = asyncio.Event()

        async def collect_mcp_requests() -> None:
            while True:
                raw = await websocket.recv()
                payload = json.loads(raw)
                if payload.get("type") != "mcp_request":
                    continue
                request_id = payload.get("request_id")
                if isinstance(request_id, str):
                    received_request_ids.append(request_id)
                    request_received.set()
                    return

        collector_task = asyncio.create_task(collect_mcp_requests())
        skip_payload = json.dumps(
            {
                "device_id": device_id,
                "request_id": f"req-skip-{unique_id}",
                "method": "tools/list",
                "params": {},
                "origin_pod": FRONTEND_TUNNEL_POD_ID,
            }
        )
        _ = await frontend_container.redis_client.publish(TUNNEL_MCP_REQUEST_CHANNEL, skip_payload)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(request_received.wait(), timeout=2.0)
        collector_task.cancel()
        try:
            await collector_task
        except asyncio.CancelledError:
            pass

        assert received_request_ids == []

        deliver_payload = json.dumps(
            {
                "device_id": device_id,
                "request_id": f"req-deliver-{unique_id}",
                "method": "tools/list",
                "params": {},
                "origin_pod": f"pod-b-{unique_id}",
            }
        )
        request_received = asyncio.Event()
        collector_task = asyncio.create_task(collect_mcp_requests())
        _ = await frontend_container.redis_client.publish(TUNNEL_MCP_REQUEST_CHANNEL, deliver_payload)
        await asyncio.wait_for(request_received.wait(), timeout=5.0)
        collector_task.cancel()
        try:
            await collector_task
        except asyncio.CancelledError:
            pass

    assert received_request_ids == [f"req-deliver-{unique_id}"]


@pytest.mark.asyncio
async def test_e2e_multipod_platform_mcp_device_mcp_http(
    flows_client_http: AsyncClient,
    agent_frontend_http_client: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)

        async def responder() -> None:
            while True:
                raw = await websocket.recv()
                payload = json.loads(raw)
                if payload.get("type") != "mcp_request":
                    continue
                request_id = payload.get("request_id")
                await websocket.send(
                    json.dumps(
                        {
                            "type": "mcp_response",
                            "request_id": request_id,
                            "result": {"tools": [{"name": "multipod-platform-mcp"}]},
                        }
                    )
                )
                return

        responder_task = asyncio.create_task(responder())
        response = await flows_client_http.post(
            PLATFORM_MCP_PATH,
            headers=auth_headers,
            json={
                "jsonrpc": "2.0",
                "id": 501,
                "method": "device/mcp",
                "params": {
                    "device_id": device_id,
                    "method": "tools/list",
                    "params": {},
                },
            },
        )
        await responder_task
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["tools"][0]["name"] == "multipod-platform-mcp"


@pytest.mark.asyncio
async def test_e2e_send_mcp_request_offline(
    frontend_container,
    unique_id: str,
) -> None:
    with pytest.raises(ValueError, match="offline"):
        _ = await send_mcp_request_to_device(
            frontend_container.redis_client,
            f"missing-device-{unique_id}",
            method="tools/list",
            params={},
            timeout_seconds=2.0,
        )
