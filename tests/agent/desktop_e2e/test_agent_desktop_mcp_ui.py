"""Desktop E2E: Humanitec Platform MCP visibility in Settings and chat."""

from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from apps.agent.desktop.build_contract import load_default_distro_config
from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.desktop_e2e.helpers import (
    assert_humanitec_preload_api,
    assert_platform_mcp_first_in_chat_picker,
    assert_platform_mcp_first_in_settings,
    connect_desktop_browser,
    find_main_app_page,
    pair_desktop_via_deep_link,
    read_bundled_extensions,
    wait_for_device_offline,
)


def test_mcp_bld_01_bundled_extensions_platform_mcp_first() -> None:
    extensions = read_bundled_extensions()
    assert extensions[0]["id"] == "platform_mcp"


def test_mcp_bld_02_default_extensions_platform_mcp_first() -> None:
    distro = load_default_distro_config()
    assert distro.default_extensions[0] == "platform_mcp"


def test_mcp_bld_03_platform_mcp_streamable_http_config() -> None:
    extensions = read_bundled_extensions()
    platform_mcp = extensions[0]
    assert platform_mcp["type"] == "streamable_http"
    headers = platform_mcp["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer ${HUMANITEC_DEVICE_TOKEN}"


@pytest.mark.asyncio
async def test_mcp_ui_01_first_launch_bundled_order(
    humanitec_desktop_process_factory,
) -> None:
    extensions = read_bundled_extensions()
    assert extensions[0]["display_name"] == "Humanitec"
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await assert_humanitec_preload_api(page)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_ui_02_after_pairing_enabled(
    agent_frontend_http_client,
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
        assert credentials["platform_mcp_url"]
        assert credentials["token"]
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await assert_platform_mcp_first_in_settings(page)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_ui_03_chat_mcp_picker_order(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
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
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_ui_04_flow_tools_visible_via_platform_mcp(
    agent_frontend_http_client,
    auth_token: str,
    flows_client_http,
    unique_id: str,
    humanitec_desktop_process_factory,
) -> None:
    from tests.agent.fixtures.flow_archetypes import ensure_react_flow

    flow_id = await ensure_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        _device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        from httpx import AsyncClient

        async with AsyncClient(timeout=30.0) as mcp_client:
            response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
        assert response.status_code == 200
        tools = response.json()["result"]["tools"]
        tool_names = {tool["name"] for tool in tools if isinstance(tool, dict)}
        assert f"flow_{flow_id}" in tool_names
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_ui_05_post_revoke_credentials_cleared(
    agent_frontend_http_client,
    auth_token: str,
    frontend_container,
    humanitec_desktop_process_factory,
) -> None:
    from apps.agent.service import TOKEN_DENY_PREFIX

    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        device_id, credentials = await pair_desktop_via_deep_link(
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
        from httpx import AsyncClient

        async with AsyncClient(timeout=30.0) as mcp_client:
            response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
        assert response.status_code == 401
        body = response.json()
        assert "error" in body or body.get("detail")
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_g_01_empty_chat_picker_platform_mcp_first(
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await assert_platform_mcp_first_in_chat_picker(page)
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_g_02_flow_description_in_tools_list(
    agent_frontend_http_client,
    auth_token: str,
    flows_client_http,
    unique_id: str,
    humanitec_desktop_process_factory,
) -> None:
    from tests.agent.fixtures.flow_archetypes import ensure_react_flow_with_description

    flow_description = f"Humanitec picker description {unique_id}"
    flow_id = await ensure_react_flow_with_description(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
        description=flow_description,
    )
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        _device_id, credentials = await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        from httpx import AsyncClient

        async with AsyncClient(timeout=30.0) as mcp_client:
            response = await mcp_client.post(
                credentials["platform_mcp_url"],
                headers={"Authorization": f"Bearer {credentials['token']}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
        assert response.status_code == 200
        tools = response.json()["result"]["tools"]
        matched = [
            tool
            for tool in tools
            if isinstance(tool, dict) and tool.get("name") == f"flow_{flow_id}"
        ]
        assert len(matched) == 1
        tool_description = matched[0].get("description")
        assert isinstance(tool_description, str)
        assert flow_description in tool_description
        async with async_playwright() as playwright:
            browser = await connect_desktop_browser(playwright, desktop)
            page = await find_main_app_page(browser)
            await assert_platform_mcp_first_in_chat_picker(page)
            body_text = await page.locator("body").inner_text()
            assert flow_description in body_text or flow_id in body_text
    finally:
        desktop.stop()


@pytest.mark.asyncio
async def test_mcp_ui_06_env_applied_at_startup(
    agent_frontend_http_client,
    auth_token: str,
    humanitec_desktop_process_factory,
) -> None:
    desktop = humanitec_desktop_process_factory()
    try:
        desktop.start()
        await pair_desktop_via_deep_link(
            desktop,
            agent_frontend_http_client,
            auth_token,
        )
        credentials = desktop.read_credentials()
        assert credentials["platform_mcp_url"]
        desktop.stop()
        desktop.start()
        restarted_credentials = desktop.wait_for_credentials(timeout_seconds=30.0)
        assert restarted_credentials["platform_mcp_url"] == credentials["platform_mcp_url"]
    finally:
        desktop.stop()
