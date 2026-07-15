"""L4 acceptance: Settings + chat + Platform MCP сквозные сценарии."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.agent._helpers import (
    AGENT_API_PREFIX,
    assert_audit_event_in_redis,
    company_id_from_auth_token,
)
from tests.agent.desktop_e2e.conftest import PairedDesktopDeepLink, PairedDesktopUiSession
from tests.agent.desktop_e2e.helpers import (
    assert_platform_mcp_first_in_chat_picker,
    assert_platform_mcp_first_in_settings,
    send_chat_message,
    wait_for_device_offline,
)
from tests.agent.fixtures.flow_archetypes import ensure_failed_flow, ensure_interrupt_flow


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_g_int_chat_interrupt_resume(
    paired_desktop_ui_session: PairedDesktopUiSession,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_interrupt_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    context_id = f"l4-int-{unique_id}"
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Name?"}},
            {"type": "text", "content": "Done L4"},
        ]
    )
    credentials = paired_desktop_ui_session.credentials
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
        assert first.json()["result"]["task_state"] == "input-required"
        second = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_id}",
                    "arguments": {"message": "Ivan", "context_id": context_id},
                },
            },
        )
    assert second.status_code == 200
    assert second.json()["result"]["task_state"] == "completed"
    page = paired_desktop_ui_session.page
    await assert_platform_mcp_first_in_chat_picker(page)
    await send_chat_message(page, f"resume flow {flow_id}")


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_g_04_two_flows_in_session(
    paired_desktop_deep_link: PairedDesktopDeepLink,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    from tests.agent.fixtures.flow_archetypes import ensure_react_flow

    _ = flows_service, flows_worker
    flow_a = await ensure_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        f"a-{unique_id}",
    )
    flow_b = await ensure_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        f"b-{unique_id}",
    )
    await mock_llm_with_queue(
        [
            {"type": "text", "content": "Flow A"},
            {"type": "text", "content": "Flow B"},
        ]
    )
    credentials = paired_desktop_deep_link.credentials
    async with AsyncClient(timeout=60.0) as mcp_client:
        first = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_a}",
                    "arguments": {"message": "first"},
                },
            },
        )
        second = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_b}",
                    "arguments": {"message": "second"},
                },
            },
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result"]["task_state"] == "completed"
    assert second.json()["result"]["task_state"] == "completed"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_g_05_failed_flow_in_chat(
    paired_desktop_ui_session: PairedDesktopUiSession,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_failed_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    credentials = paired_desktop_ui_session.credentials
    async with AsyncClient(timeout=60.0) as mcp_client:
        response = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_id}",
                    "arguments": {"message": "fail please"},
                },
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert "error" in body or body.get("result", {}).get("task_state") == "failed"
    await send_chat_message(paired_desktop_ui_session.page, f"failed flow {flow_id}")


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_acc_02_settings_picker_interrupt_flow(
    paired_desktop_ui_session: PairedDesktopUiSession,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_interrupt_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "City?"}},
            {"type": "text", "content": "Thanks"},
        ]
    )
    page = paired_desktop_ui_session.page
    await assert_platform_mcp_first_in_chat_picker(page)
    await send_chat_message(page, f"flow {flow_id} interrupt test")


@pytest.mark.asyncio
async def test_acc_05_in_flight_revoke_tunnel_offline(
    paired_desktop_deep_link: PairedDesktopDeepLink,
    agent_frontend_http_client: AsyncClient,
) -> None:
    device_id = paired_desktop_deep_link.device_id
    delete_response = await agent_frontend_http_client.delete(f"{AGENT_API_PREFIX}/devices/{device_id}")
    assert delete_response.status_code in {200, 204}
    await wait_for_device_offline(agent_frontend_http_client, device_id)
    paired_desktop_deep_link.desktop.wait_for_credentials_cleared()


@pytest.mark.asyncio
async def test_acc_01_settings_extensions_order_after_pair(
    paired_desktop_ui_session: PairedDesktopUiSession,
) -> None:
    await assert_platform_mcp_first_in_settings(paired_desktop_ui_session.page)


@pytest.mark.asyncio
async def test_acc_03_discover_download_matches_local_release(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact,
) -> None:
    from pathlib import Path

    from apps.agent.config import reset_agent_settings
    from scripts.agent_build import detect_host_platform
    from tests.agent.fixtures.local_releases import require_local_release_asset_name

    reset_agent_settings()
    platform_name = detect_host_platform()
    asset_name = require_local_release_asset_name(Path(agent_local_release_artifact))
    discover_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/discover")
    assert discover_response.status_code == 200
    releases = discover_response.json()["releases"]
    assert releases["ready"] is True
    download_response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=False,
    )
    assert download_response.status_code == 307
    location = download_response.headers.get("location")
    assert isinstance(location, str)
    assert "/releases/artifact/" in location
    assert asset_name in location or platform_name in location


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_acc_04_audit_after_platform_mcp_call(
    paired_desktop_deep_link: PairedDesktopDeepLink,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    frontend_container,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    from tests.agent.fixtures.flow_archetypes import ensure_react_flow

    _ = flows_service, flows_worker
    flow_id = await ensure_react_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    await mock_llm_with_queue([{"type": "text", "content": "Audit ACC-04"}])
    credentials = paired_desktop_deep_link.credentials
    async with AsyncClient(timeout=60.0) as mcp_client:
        response = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_id}",
                    "arguments": {"message": "audit acc04"},
                },
            },
        )
    assert response.status_code == 200
    company_id = company_id_from_auth_token(auth_token)
    await assert_audit_event_in_redis(
        frontend_container,
        company_id=company_id,
        event_type="agent.platform_mcp.tools_call",
    )


@pytest.mark.asyncio
async def test_acc_06_second_device_in_list(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
    paired_desktop_deep_link: PairedDesktopDeepLink,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    _ = paired_desktop_deep_link
    first_device_id, _first_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"a-{unique_id}",
    )
    second_device_id, _second_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=f"b-{unique_id}",
    )
    list_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    device_ids = {item["device_id"] for item in items if isinstance(item, dict)}
    assert first_device_id in device_ids
    assert second_device_id in device_ids


@pytest.mark.asyncio
async def test_acc_07_policy_toggle_via_api(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> None:
    from tests.agent._helpers import pair_and_register_device

    device_id, _token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    devices_response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/devices")
    assert devices_response.status_code == 200
    items = devices_response.json()["items"]
    matched = [item for item in items if item.get("device_id") == device_id]
    assert len(matched) == 1
    policy_before = matched[0]["policy"]
    assert isinstance(policy_before, dict)
    shell_before = policy_before["shell_enabled"]
    patch_response = await agent_frontend_http_client.patch(
        f"{AGENT_API_PREFIX}/devices/{device_id}/policy",
        json={"policy": {**policy_before, "shell_enabled": not shell_before}},
    )
    assert patch_response.status_code == 200
    policy_after = patch_response.json()["policy"]
    assert policy_after["shell_enabled"] is not shell_before


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_acc_08_golden_pair_mcp_picker_interrupt(
    paired_desktop_ui_session: PairedDesktopUiSession,
    auth_token: str,
    flows_client_http: AsyncClient,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_interrupt_flow(
        flows_client_http,
        {"Authorization": f"Bearer {auth_token}"},
        unique_id,
    )
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Step?"}},
            {"type": "text", "content": "Golden L4"},
        ]
    )
    credentials = paired_desktop_ui_session.credentials
    async with AsyncClient(timeout=60.0) as mcp_client:
        response = await mcp_client.post(
            credentials["platform_mcp_url"],
            headers={"Authorization": f"Bearer {credentials['token']}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": f"flow_{flow_id}",
                    "arguments": {"message": "golden"},
                },
            },
        )
    assert response.status_code == 200
    await assert_platform_mcp_first_in_chat_picker(paired_desktop_ui_session.page)


@pytest.mark.asyncio
async def test_acc_09_no_goose_provider_onboarding(
    paired_desktop_ui_session: PairedDesktopUiSession,
) -> None:
    page = paired_desktop_ui_session.page
    await page.wait_for_selector("[data-humanitec-chat-composer]", timeout=10_000)
    pairing_inputs = await page.locator("[data-humanitec-pairing-code]").count()
    assert pairing_inputs == 0
    goose_onboarding = await page.get_by_text("Connect an AI model provider").count()
    assert goose_onboarding == 0
