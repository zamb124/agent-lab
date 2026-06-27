"""Desktop E2E: pairing, tunnel, platform MCP через HumanitecAgent."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.frontend.config import get_frontend_public_base_url
from tests.agent._helpers import (
    AGENT_API_PREFIX,
    assert_audit_event_in_redis,
    company_id_from_auth_token,
    ensure_example_react_flow,
    pair_and_register_device,
)
from tests.agent.desktop_e2e.helpers import pair_desktop_via_deep_link
from tests.agent.desktop_e2e.pairing_helper import fetch_pairing_code_from_settings


@pytest.mark.asyncio
async def test_d5_register_url_bundle(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    pairing_response = await agent_frontend_http_client.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing_response.status_code == 200
    pairing_code = pairing_response.json()["pairing_code"]
    device_id = f"device-bundle-{unique_id}"
    response = await agent_frontend_http_client.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing_code,
            "device_id": device_id,
            "device_name": f"Bundle {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    base = get_frontend_public_base_url()
    assert body["frontend_base_url"] == base
    assert body["tunnel_ws_url"] == "ws://system.lvh.me:9004/frontend/api/agent/tunnel"
    assert body["company_id"] == company_id_from_auth_token(auth_token)
    assert body["platform_mcp_url"] == f"{base}/flows/api/v1/agent/platform-mcp"


@pytest.mark.asyncio
async def test_d8_tunnel_online_after_register(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, _credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        list_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        matched = next(item for item in items if item["device_id"] == device_id)
        assert matched["is_tunnel_online"] is True
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d9_tunnel_policy_frame(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, _credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        list_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        matched = next(item for item in items if item["device_id"] == device_id)
        policy = matched["policy"]
        assert isinstance(policy, dict)
        assert policy["browser_enabled"] is True
        assert policy["shell_enabled"] is False
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d10_platform_mcp_tools_list(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        _device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with AsyncClient(timeout=30.0) as mcp_client:
            response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
        assert response.status_code == 200
        assert "result" in response.json()
    finally:
        desktop.stop()


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_d11_platform_mcp_tools_call(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
    humanitec_desktop_process_factory,
) -> None:
    _ = flows_service, flows_worker
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        _device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        flow_id = await ensure_example_react_flow(
            flows_client_http,
            {"Authorization": f"Bearer {auth_token}"},
            unique_id,
        )
        await mock_llm_with_queue([{"type": "text", "content": "desktop e2e ok"}])
        async with AsyncClient(timeout=60.0) as mcp_client:
            response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{flow_id}",
                        "arguments": {"message": "desktop golden path"},
                    },
                },
            )
        assert response.status_code == 200
        assert "result" in response.json()
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d14_second_company_isolation(
    agent_frontend_http_client: AsyncClient,
    agent_frontend_http_company2: AsyncClient,
    auth_token: str,
    auth_token_company2: str,
    flows_client_http: AsyncClient,
    unique_id: str,
) -> None:
    _ = auth_token
    device_id_a, _token_a = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"company-a-{unique_id}",
    )
    _device_id_b, _token_b = await pair_and_register_device(
        agent_frontend_http_company2,
        auth_cookie=auth_token_company2,
        unique_id=f"company-b-{unique_id}",
    )
    flow_id = await ensure_example_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        f"iso-{unique_id}",
    )
    list_a = await flows_client_http.post(
        "/flows/api/v1/agent/platform-mcp",
        headers={"Cookie": f"auth_token={auth_token}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )
    assert list_a.status_code == 200
    tool_names_a = {
        tool["name"] for tool in list_a.json()["result"]["tools"] if isinstance(tool, dict)
    }
    assert f"flow_{flow_id}" in tool_names_a
    list_b = await flows_client_http.post(
        "/flows/api/v1/agent/platform-mcp",
        headers={"Cookie": f"auth_token={auth_token_company2}"},
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
    )
    assert list_b.status_code == 200
    tool_names_b = {
        tool["name"] for tool in list_b.json()["result"]["tools"] if isinstance(tool, dict)
    }
    assert f"flow_{flow_id}" not in tool_names_b
    _ = device_id_a


@pytest.mark.asyncio
async def test_d15_device_mcp_offline(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    flows_client_http: AsyncClient,
) -> None:
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"offline-{unique_id}",
    )
    response = await flows_client_http.post(
        "/flows/api/v1/agent/platform-mcp",
        headers={"Cookie": f"auth_token={auth_token}"},
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "device/mcp",
            "params": {
                "device_id": device_id,
                "method": "tools/list",
                "params": {},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32000
    assert "offline" in body["error"]["message"].lower()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.real_taskiq
async def test_d_gold_pairing_tunnel_mcp_audit(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    ui_page_system,
    agent_desktop_base_url: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
    frontend_container,
    humanitec_desktop_process_factory,
) -> None:
    _ = flows_service, flows_worker
    company_id = company_id_from_auth_token(auth_token)
    pairing_code = await fetch_pairing_code_from_settings(
        ui_page_system,
        f"{agent_desktop_base_url}/settings",
    )

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        desktop.pair_via_deep_link(pairing_code)
        credentials = desktop.wait_for_credentials()
        device_id = credentials["device_id"]
        await desktop.wait_for_tunnel_online(agent_frontend_http_client, device_id)

        flow_id = await ensure_example_react_flow(
            flows_client_http,
            {"Cookie": f"auth_token={auth_token}"},
            unique_id,
        )
        await mock_llm_with_queue([{"type": "text", "content": "D-GOLD ok"}])
        async with AsyncClient(timeout=60.0) as mcp_client:
            call_response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{flow_id}",
                        "arguments": {"message": "golden"},
                    },
                },
            )
        assert call_response.status_code == 200
        await assert_audit_event_in_redis(
            frontend_container,
            company_id=company_id,
            event_type="agent.device_registered",
        )
    finally:
        desktop.stop()
