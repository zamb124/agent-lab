"""
Platform MCP (browser, search): flows API test/sync против реальных peer-сервисов.

Отдельно от stub-тестов в test_mcp.py — здесь проверяется цепочка
POST /flows/api/v1/mcp/servers/{platform_id}/test|sync → HTTP MCP peer.
"""

from __future__ import annotations

import pytest

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.mcp_sync import ensure_default_mcp_servers_for_company
from core.integrations.mcp import mcp_tool_reference_id

pytest_plugins = ["tests.search.conftest"]


@pytest.mark.asyncio
async def test_platform_search_mcp_test_endpoint(search_service, client, container) -> None:
    """Default server `search` → POST .../test возвращает 3 tools через Search MCP."""
    _ = search_service
    runtime = as_flow_runtime_container(container)
    servers = await ensure_default_mcp_servers_for_company(container=runtime)
    search_server = next(item for item in servers if item.server_id == "search")
    expected_url = f"{get_settings().server.get_service_url('search').rstrip('/')}/search/api/v1/mcp"
    assert search_server.url == expected_url

    test_response = await client.post("/flows/api/v1/mcp/servers/search/test")
    assert test_response.status_code == 200, test_response.text
    body = test_response.json()
    assert body["success"] is True
    assert body["tools_count"] == 3
    assert body["transport_type"] == "http"
    assert body["url"] == expected_url


@pytest.mark.asyncio
async def test_platform_search_mcp_sync_endpoint(search_service, client, container) -> None:
    """Default server `search` → POST .../sync upsert'ит tool references."""
    _ = search_service
    runtime = as_flow_runtime_container(container)
    _ = await ensure_default_mcp_servers_for_company(container=runtime)

    sync_response = await client.post("/flows/api/v1/mcp/servers/search/sync")
    assert sync_response.status_code == 200, sync_response.text
    body = sync_response.json()
    assert body["success"] is True
    assert body["tools_count"] == 3
    tool_names = sorted(tool["name"] for tool in body["tools"])
    assert tool_names == [
        "meta_web_search",
        "search_result_insights",
        "search_suggest",
    ]

    tools_response = await client.get("/flows/api/v1/tools/all")
    assert tools_response.status_code == 200
    mcp_tools = [
        tool
        for tool in tools_response.json()["items"]
        if tool.get("mcp_server_id") == "search"
    ]
    assert len(mcp_tools) == 3
    assert mcp_tool_reference_id("search", "meta_web_search") in {
        tool["tool_id"] for tool in mcp_tools
    }


@pytest.mark.asyncio
async def test_platform_search_mcp_test_returns_502_when_peer_down(client, unique_id: str) -> None:
    """Недоступный upstream → 502 (fail-closed), без silent fallback."""
    server_id = f"dead_search_{unique_id}"
    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "Dead search peer",
            "url": "http://127.0.0.1:59998/search/api/v1/mcp",
            "transport_type": "http",
        },
    )
    assert create_response.status_code == 200

    test_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/test")
    assert test_response.status_code == 502

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
