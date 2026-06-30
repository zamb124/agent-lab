"""
HTTP-тесты Platform MCP endpoint для HumanitecAgent.
"""

import pytest
from httpx import AsyncClient

from apps.flows.src.container import get_container as get_flows_container

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
async def test_platform_mcp_discover_rejects_event_stream(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.get(
        PLATFORM_MCP_PATH,
        headers={**auth_headers, "Accept": "text/event-stream"},
    )
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_platform_mcp_initialize(
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
    assert body["id"] == 2
    assert body["result"]["protocolVersion"] == "2024-11-05"
    assert body["result"]["serverInfo"]["name"] == "Humanitec Platform MCP"
    assert response.headers.get("Mcp-Session-Id")


@pytest.mark.asyncio
async def test_platform_mcp_notifications_initialized(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.asyncio
async def test_platform_mcp_ping(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 5, "method": "ping"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 5
    assert body["result"] == {}


@pytest.mark.asyncio
async def test_platform_mcp_unknown_method(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 9, "method": "foo/bar", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32601


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
    tools = body["result"]["tools"]
    assert isinstance(tools, list)
    names: set[str] = {str(tool["name"]) for tool in tools}
    assert any(name.startswith("tool_") for name in names)
    assert "tool_calculator" in names


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_builtin_tool(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "tool_calculator",
                "arguments": {"expression": "2+2"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "error" not in body
    content = body["result"]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[0]["text"]


@pytest.mark.asyncio
async def test_platform_mcp_flow_sticky_context_id(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    session_id = f"mcp-session-{unique_id}"
    flow_id = f"missing_flow_{unique_id}"
    call_payload = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": f"flow_{flow_id}",
            "arguments": {"message": "hello"},
        },
    }
    headers = {**auth_headers, "Mcp-Session-Id": session_id}

    first = await flows_client.post(PLATFORM_MCP_PATH, headers=headers, json=call_payload)
    assert first.status_code == 200

    container = get_flows_container()
    redis_key = f"agent_mcp_session:{session_id}:flow:{flow_id}"
    stored_after_first = await container.redis_client.get(redis_key)
    assert stored_after_first

    second = await flows_client.post(PLATFORM_MCP_PATH, headers=headers, json=call_payload)
    assert second.status_code == 200
    stored_after_second = await container.redis_client.get(redis_key)
    assert stored_after_second == stored_after_first


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
