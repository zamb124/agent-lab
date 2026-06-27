"""Невозможные / negative Platform MCP сценарии."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.agent.service import TOKEN_DENY_PREFIX
from tests.agent._helpers import AGENT_API_PREFIX, PLATFORM_MCP_PATH, pair_and_register_device
from tests.agent.fixtures.flow_archetypes import ensure_react_flow


@pytest.mark.asyncio
async def test_imp_platform_mcp_other_company_flow(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_company2: dict[str, str],
    flows_service: None,
    unique_id: str,
) -> None:
    _ = flows_service
    flow_id = await ensure_react_flow(
        flows_client_http,
        auth_headers,
        f"iso-{unique_id}",
    )
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers_company2,
        json={
            "jsonrpc": "2.0",
            "id": 401,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "cross company"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_imp_device_mcp_foreign_device_id(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 402,
            "method": "device/mcp",
            "params": {
                "device_id": "device-foreign-not-registered",
                "method": "tools/list",
                "params": {},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_imp_platform_mcp_invalid_json(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        content=b"{not-json",
    )
    assert response.status_code >= 400


@pytest.mark.asyncio
async def test_imp_platform_mcp_device_mcp_via_tools_call(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 403,
            "method": "tools/call",
            "params": {
                "name": "device_mcp",
                "arguments": {"message": "nope"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_imp_platform_mcp_device_mcp_missing_method(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    flows_service: None,
    unique_id: str,
) -> None:
    _ = flows_service
    device_id, _token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"missing-method-{unique_id}",
    )
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 404,
            "method": "device/mcp",
            "params": {
                "device_id": device_id,
                "params": {},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_imp_register_wrong_pairing_code(
    agent_frontend_http_anon: AsyncClient,
    unique_id: str,
    flows_service: None,
) -> None:
    _ = flows_service
    response = await agent_frontend_http_anon.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": "999999",
            "device_id": f"device-wrong-{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 400
    assert "pairing" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_imp_platform_mcp_tools_list_without_auth(
    flows_client_http: AsyncClient,
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_imp_platform_mcp_revoked_device_jwt_returns_401(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    unique_id: str,
) -> None:
    _ = flows_service
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"revoked-jwt-{unique_id}",
    )
    delete_response = await agent_frontend_http_client.delete(
        f"/frontend/api/agent/devices/{device_id}"
    )
    assert delete_response.status_code in {200, 204}
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers={"Authorization": f"Bearer {device_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_imp_platform_mcp_revoked_device_token_denied_in_storage(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    frontend_container,
    unique_id: str,
    flows_service: None,
) -> None:
    _ = flows_service
    device_id, device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"revoked-{unique_id}",
    )
    delete_response = await agent_frontend_http_client.delete(
        f"/frontend/api/agent/devices/{device_id}"
    )
    assert delete_response.status_code in {200, 204}
    deny_raw = await frontend_container.shared_storage.get(
        f"{TOKEN_DENY_PREFIX}{device_id}",
        force_global=True,
    )
    assert deny_raw is not None
    response = await agent_frontend_http_client.get("/frontend/api/agent/devices")
    assert response.status_code == 200
    items = response.json()["items"]
    matched = next(item for item in items if item["device_id"] == device_id)
    assert matched["is_tunnel_online"] is False
    _ = device_token

