"""Desktop E2E: auth deep link, pairing deep link, device MCP, revoke."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from playwright.async_api import async_playwright

from apps.agent.service import TOKEN_DENY_PREFIX
from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.desktop_e2e.helpers import (
    create_pairing_code,
    find_pairing_page,
    pair_desktop_via_deep_link,
    submit_pairing_code_in_ui,
    wait_for_device_offline,
)
from tests.agent.desktop_e2e.pairing_helper import fetch_pairing_code_from_settings


@pytest.mark.asyncio
async def test_d5_auth_device_token_deep_link(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        desktop.auth_via_deep_link(auth_token)
        credentials = desktop.wait_for_credentials()
        assert credentials["device_id"] != "pending"
        assert credentials["llm_api_base_url"]
        assert credentials["llm_provider_id"] == "humanitec"
        assert credentials["llm_model_id"] == "auto"
        assert credentials["tunnel_ws_url"]
        assert credentials["platform_mcp_url"]
    finally:
        desktop.stop()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_d6_pairing_deep_link_playwright(
    agent_frontend_http_client: AsyncClient,
    ui_page_system,
    auth_token: str,
    unique_id: str,
    agent_desktop_base_url: str,
    humanitec_desktop_process_factory,
) -> None:
    _ = agent_frontend_http_client, auth_token, unique_id
    pairing_code = await fetch_pairing_code_from_settings(
        ui_page_system,
        f"{agent_desktop_base_url}/settings",
    )
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        desktop.pair_via_deep_link(pairing_code)
        credentials = desktop.wait_for_credentials()
        assert credentials["device_id"] != "pending"
        device_id = credentials["device_id"]
        device_item = await desktop.wait_for_tunnel_online(
            agent_frontend_http_client,
            device_id,
        )
        assert device_item["is_tunnel_online"] is True
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d7_manual_pairing_ui(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    humanitec_desktop_process_factory,
) -> None:
    _ = unique_id
    pairing_code = await create_pairing_code(agent_frontend_http_client, auth_token)
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        desktop.open_pairing_ui_deep_link()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{desktop.remote_debugging_port}"
            )
            page = await find_pairing_page(browser)
            await submit_pairing_code_in_ui(page, pairing_code)
        credentials = desktop.wait_for_credentials()
        assert credentials["device_id"] != "pending"
        await desktop.wait_for_tunnel_online(
            agent_frontend_http_client,
            credentials["device_id"],
        )
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d12_device_mcp_roundtrip(
    agent_frontend_http_client: AsyncClient,
    flows_client_http: AsyncClient,
    auth_token: str,
    unique_id: str,
    humanitec_desktop_process_factory,
) -> None:
    _ = unique_id
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        response = await flows_client_http.post(
            "/flows/api/v1/agent/platform-mcp",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 42,
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
        assert body["result"] == {"tools": []}
        assert credentials["platform_mcp_url"]
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d12_device_mcp_tools_call_unavailable(
    agent_frontend_http_client: AsyncClient,
    flows_client_http: AsyncClient,
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
        response = await flows_client_http.post(
            "/flows/api/v1/agent/platform-mcp",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "jsonrpc": "2.0",
                "id": 43,
                "method": "device/mcp",
                "params": {
                    "device_id": device_id,
                    "method": "tools/call",
                    "params": {"name": "missing_tool", "arguments": {}},
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "error" in body
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d13_revoke_mid_session_tunnel_closed(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    frontend_container,
    humanitec_desktop_process_factory,
) -> None:
    _ = unique_id
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, _credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        delete_response = await agent_frontend_http_client.delete(
            f"{AGENT_API_PREFIX}/devices/{device_id}"
        )
        assert delete_response.status_code in {200, 204}
        desktop.wait_for_credentials_cleared()
        await wait_for_device_offline(agent_frontend_http_client, device_id)
        deny_raw = await frontend_container.shared_storage.get(
            f"{TOKEN_DENY_PREFIX}{device_id}",
            force_global=True,
        )
        assert deny_raw is not None
    finally:
        desktop.stop()
