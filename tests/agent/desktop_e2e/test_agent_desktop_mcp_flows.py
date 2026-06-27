"""Desktop E2E: Platform MCP flow archetypes через paired HumanitecAgent."""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient
from playwright.async_api import async_playwright

from tests.agent._helpers import (
    PLATFORM_MCP_PATH,
    assert_audit_event_in_redis,
    company_id_from_auth_token,
)
from tests.agent.desktop_e2e.helpers import (
    assert_platform_mcp_first_in_chat_picker,
    connect_desktop_browser,
    find_main_app_page,
    pair_desktop_via_deep_link,
    send_chat_message,
)
from tests.agent.fixtures.flow_archetypes import ensure_interrupt_flow


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_d_flow_03_desktop_mcp_interrupt_resume(
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
    flow_id = await ensure_interrupt_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    context_id = f"desktop-ctx-{unique_id}"
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Your name?"}},
            {"type": "text", "content": "Hello Desktop User"},
        ]
    )
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        _device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with AsyncClient(timeout=60.0) as mcp_client:
            first = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{flow_id}",
                        "arguments": {"message": "start", "context_id": context_id},
                    },
                },
            )
            assert first.status_code == 200
            first_body = first.json()
            assert first_body["result"]["task_state"] == "input-required"
            second = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{flow_id}",
                        "arguments": {"message": "Desktop User", "context_id": context_id},
                    },
                },
            )
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["result"]["task_state"] == "completed"
    finally:
        desktop.stop()


@pytest.mark.asyncio
@pytest.mark.real_taskiq
@pytest.mark.e2e
async def test_mcp_g_03_chat_select_platform_mcp_flow_tool(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
    humanitec_desktop_process_factory,
) -> None:
    from tests.agent.fixtures.flow_archetypes import ensure_react_flow

    _ = flows_service, flows_worker
    flow_id = await ensure_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    await mock_llm_with_queue([{"type": "text", "content": "Chat MCP ok"}])
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await assert_platform_mcp_first_in_chat_picker(page)
            await send_chat_message(page, f"call flow {flow_id}")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_d11_local_mcp_url_proxy_via_device_mcp(
    local_mcp_http_url: str,
    agent_frontend_http_client: AsyncClient,
    flows_client_http: AsyncClient,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    previous_local_mcp_url = os.environ.get("HUMANITEC_LOCAL_MCP_URL")
    os.environ["HUMANITEC_LOCAL_MCP_URL"] = local_mcp_http_url
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, _credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        await desktop.wait_for_tunnel_online(agent_frontend_http_client, device_id)
        response = await flows_client_http.post(
            PLATFORM_MCP_PATH,
            headers={"Authorization": f"Bearer {auth_token}"},
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
        assert response.status_code == 200
        body = response.json()
        tool_names = {
            tool["name"]
            for tool in body["result"]["tools"]
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        assert "stub_resolve_library" in tool_names
    finally:
        if previous_local_mcp_url is None:
            os.environ.pop("HUMANITEC_LOCAL_MCP_URL", None)
        else:
            os.environ["HUMANITEC_LOCAL_MCP_URL"] = previous_local_mcp_url
        desktop.stop()


@pytest.mark.asyncio
async def test_d12_device_mcp_audit(
    agent_frontend_http_client: AsyncClient,
    flows_client_http: AsyncClient,
    auth_token: str,
    frontend_container,
    unique_id: str,
    humanitec_desktop_process_factory,
) -> None:
    company_id = company_id_from_auth_token(auth_token)
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
        assert "result" in response.json()
        await assert_audit_event_in_redis(
            frontend_container,
            company_id=company_id,
            event_type="agent.platform_mcp.device_mcp",
        )
    finally:
        desktop.stop()
