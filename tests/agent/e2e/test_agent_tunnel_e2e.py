"""E2E HumanitecAgent tunnel через real WebSocket (:9004)."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from httpx import AsyncClient

from apps.agent.models import DevicePolicy
from apps.agent.service import DEVICE_KEY_PREFIX, TUNNEL_ONLINE_PREFIX
from core.utils.tokens import TokenService
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    company_id_from_auth_token,
    pair_and_register_device,
    user_id_from_auth_token,
)
from tests.agent._realtime_helpers import (
    AGENT_TUNNEL_WS_PATH,
    FRONTEND_WS_BASE,
    connect_agent_tunnel_ws,
    expect_tunnel_rejected,
    wait_tunnel_error_frame,
    wait_tunnel_json,
)


@pytest.mark.asyncio
async def test_e2e_tunnel_ping_pong(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        policy_frame = await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        assert isinstance(policy_frame.get("policy"), dict)
        await websocket.send(json.dumps({"type": "ping"}))
        pong = await wait_tunnel_json(websocket, expected_type="pong", timeout=5.0)
        assert pong.get("type") == "pong"


@pytest.mark.asyncio
async def test_e2e_tunnel_invalid_token_rejected(unique_id: str) -> None:
    ws_uri = f"ws://127.0.0.1:9004/frontend/api/agent/tunnel?token=invalid-{unique_id}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4401})
    assert close_code == 4401


@pytest.mark.asyncio
async def test_e2e_tunnel_revoke_blocks_reconnect(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    revoke_response = await agent_frontend_http_client.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert revoke_response.status_code == 204
    ws_uri = f"ws://127.0.0.1:9004/frontend/api/agent/tunnel?token={device_token}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4401, 4403})
    assert close_code in {4401, 4403}


@pytest.mark.asyncio
async def test_e2e_tunnel_policy_blocks_connection(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    raw_device = await frontend_container.shared_storage.get(device_key, force_global=True)
    assert raw_device is not None
    device_payload = json.loads(raw_device)
    device_payload["policy"] = DevicePolicy(
        shell_enabled=False,
        browser_enabled=False,
        allowed_roots=[],
    ).model_dump()
    await frontend_container.shared_storage.set(device_key, json.dumps(device_payload), force_global=True)

    ws_uri = f"ws://127.0.0.1:9004/frontend/api/agent/tunnel?token={device_token}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4403})
    assert close_code == 4403


@pytest.mark.asyncio
async def test_e2e_tunnel_mcp_roundtrip(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    from apps.agent.tunnel_bus import send_mcp_request_to_device

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
                            "result": {"tools": [{"name": "local"}]},
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
        assert result == {"tools": [{"name": "local"}]}


@pytest.mark.asyncio
async def test_e2e_tunnel_wrong_token_purpose(
    auth_token: str,
    unique_id: str,
) -> None:
    ws_uri = f"{FRONTEND_WS_BASE}{AGENT_TUNNEL_WS_PATH}?token={auth_token}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4401})
    assert close_code == 4401


@pytest.mark.asyncio
async def test_e2e_tunnel_pending_device_id_token(
    auth_token: str,
    unique_id: str,
) -> None:
    user_id = user_id_from_auth_token(auth_token)
    company_id = company_id_from_auth_token(auth_token)
    token_service = TokenService()
    pending_token = token_service.create_token(
        user_id=user_id,
        company_id=company_id,
        metadata={"token_purpose": "device", "device_id": "pending"},
    )
    ws_uri = f"{FRONTEND_WS_BASE}{AGENT_TUNNEL_WS_PATH}?token={pending_token}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4401})
    assert close_code == 4401


@pytest.mark.asyncio
async def test_e2e_tunnel_inactive_device(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    device_key = f"{DEVICE_KEY_PREFIX}{device_id}"
    raw_device = await frontend_container.shared_storage.get(device_key, force_global=True)
    assert raw_device is not None
    device_payload = json.loads(raw_device)
    device_payload["is_active"] = False
    await frontend_container.shared_storage.set(device_key, json.dumps(device_payload), force_global=True)

    ws_uri = f"{FRONTEND_WS_BASE}{AGENT_TUNNEL_WS_PATH}?token={device_token}"
    close_code = await expect_tunnel_rejected(ws_uri, expected_codes={4403})
    assert close_code == 4403


@pytest.mark.asyncio
async def test_e2e_tunnel_mcp_timeout(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
    agent_tunnel_bus_pod_b: None,
) -> None:
    from apps.agent.tunnel_bus import send_mcp_request_to_device

    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        with pytest.raises(ValueError, match="Device tunnel offline"):
            _ = await send_mcp_request_to_device(
                frontend_container.redis_client,
                device_id,
                method="tools/list",
                params={},
                timeout_seconds=0.5,
            )


@pytest.mark.asyncio
async def test_e2e_tunnel_unsupported_message_type(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        await websocket.send(json.dumps({"type": "unknown_payload"}))
        error_frame = await wait_tunnel_error_frame(
            websocket,
            error_code="unsupported_message_type",
            timeout=5.0,
        )
        assert error_frame.get("type") == "error"


@pytest.mark.asyncio
async def test_e2e_tunnel_mcp_response_unknown_request_id(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    _device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        await websocket.send(
            json.dumps(
                {
                    "type": "mcp_response",
                    "request_id": f"missing-{unique_id}",
                    "result": {"tools": []},
                }
            )
        )
        error_frame = await wait_tunnel_error_frame(
            websocket,
            error_code="unknown_mcp_request",
            timeout=5.0,
        )
        assert error_frame.get("type") == "error"


@pytest.mark.asyncio
async def test_e2e_tunnel_online_ttl_refresh_after_ping(
    agent_frontend_http_client: AsyncClient,
    frontend_container,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    tunnel_online_key = f"{TUNNEL_ONLINE_PREFIX}{device_id}"
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        await frontend_container.shared_storage.delete(tunnel_online_key, force_global=True)
        online_before = await frontend_container.shared_storage.get(tunnel_online_key, force_global=True)
        assert online_before is None
        await websocket.send(json.dumps({"type": "ping"}))
        await wait_tunnel_json(websocket, expected_type="pong", timeout=5.0)
        online_after = await frontend_container.shared_storage.get(tunnel_online_key, force_global=True)
        assert online_after is not None


@pytest.mark.asyncio
async def test_e2e_tunnel_revoke_disconnects_open_session(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
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
async def test_e2e_tunnel_policy_push_after_patch(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    updated_policy = {
        "allowed_roots": ["/srv/agent"],
        "exec_whitelist": ["ls"],
        "exec_require_confirm": False,
        "shell_enabled": True,
        "browser_enabled": False,
        "max_file_size_mb": 25,
        "audit_retention_days": 14,
    }
    async with connect_agent_tunnel_ws(device_token) as websocket:
        await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        patch_response = await agent_frontend_http_client.patch(
            f"{AGENT_API_PREFIX}/devices/{device_id}/policy",
            json={"policy": updated_policy},
        )
        assert patch_response.status_code == 200
        policy_frame = await wait_tunnel_json(websocket, expected_type="policy", timeout=5.0)
        pushed_policy = policy_frame.get("policy")
        assert isinstance(pushed_policy, dict)
        assert pushed_policy == updated_policy
