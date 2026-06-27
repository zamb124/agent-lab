"""
HTTP-тесты Platform MCP endpoint для HumanitecAgent.
"""

import pytest
from httpx import AsyncClient

PLATFORM_MCP_PATH = "/flows/api/v1/agent/platform-mcp"


@pytest.mark.asyncio
async def test_platform_mcp_discover(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.get(PLATFORM_MCP_PATH, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["protocolVersion"] == "2024-11-05"
    assert body["serverInfo"]["name"] == "Humanitec Platform MCP"


@pytest.mark.asyncio
async def test_platform_mcp_tools_list_requires_auth(flows_client: AsyncClient) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code in {401, 400}


@pytest.mark.asyncio
async def test_platform_mcp_tools_list_with_auth(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 7
    assert isinstance(body["result"]["tools"], list)


@pytest.mark.asyncio
async def test_platform_mcp_unsupported_method(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_unknown_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "flow_missing_flow_id",
                "arguments": {"message": "hello"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_bad_tool_name(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "platform_mcp_ping",
                "arguments": {"message": "hello"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602
    assert body["error"]["message"] == "Unsupported tool name"
