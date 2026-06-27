"""E2E Platform MCP через flows HTTP (:9001)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient

from tests.agent._helpers import (
    PLATFORM_MCP_PATH,
    assert_audit_event_in_redis,
    company_id_from_auth_token,
    ensure_example_react_flow,
    pair_and_register_device,
)


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_e2e_platform_mcp_tools_list(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert isinstance(body["result"]["tools"], list)


@pytest.mark.asyncio
async def test_e2e_platform_mcp_discover(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.get(PLATFORM_MCP_PATH, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["protocolVersion"] == "2024-11-05"
    assert body["serverInfo"]["name"] == "Humanitec Platform MCP"


@pytest.mark.asyncio
async def test_e2e_platform_mcp_tools_list_contains_flow(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    unique_id: str,
) -> None:
    _ = flows_service
    flow_id = await ensure_example_react_flow(flows_client_http, auth_headers, unique_id)
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    tool_names = {tool["name"] for tool in body["result"]["tools"] if isinstance(tool, dict)}
    assert f"flow_{flow_id}" in tool_names


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_e2e_platform_mcp_tools_call_success(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_example_react_flow(flows_client_http, auth_headers, unique_id)
    await mock_llm_with_queue([{"type": "text", "content": "Platform MCP E2E ok"}])
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "ping platform mcp"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert body["result"]["isError"] is False
    content = body["result"]["content"]
    assert isinstance(content, list)
    assert content[0]["text"] == "Platform MCP E2E ok"
    assert isinstance(body["result"]["context_id"], str)
    assert body["result"]["context_id"]


@pytest.mark.asyncio
async def test_e2e_platform_mcp_empty_body(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
) -> None:
    _ = flows_service
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        content=b"",
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_e2e_platform_mcp_tools_call_missing_message(
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
            "id": 2,
            "method": "tools/call",
            "params": {"name": "flow_example_react", "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_e2e_platform_mcp_device_mcp_offline(
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
            "id": 21,
            "method": "device/mcp",
            "params": {
                "device_id": "device-offline-e2e",
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
async def test_e2e_platform_mcp_device_mcp_missing_params(
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
            "id": 22,
            "method": "device/mcp",
            "params": {"method": "tools/list", "params": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602
    assert "device_id" in body["error"]["message"]


@pytest.mark.asyncio
async def test_e2e_platform_mcp_device_mcp_success(
    agent_frontend_http_client: AsyncClient,
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    flows_service: None,
    unique_id: str,
) -> None:
    """Registered device without active tunnel must fail offline (real roundtrip in desktop D12)."""
    _ = flows_service
    device_id, _device_token = await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 23,
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
@pytest.mark.real_taskiq
async def test_e2e_platform_mcp_context_id_continuity(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    flows_container,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
    unique_id: str,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_example_react_flow(flows_client_http, auth_headers, unique_id)
    context_id = f"ctx-{unique_id}"
    await mock_llm_with_queue(
        [
            {"type": "text", "content": "first turn"},
            {"type": "text", "content": "second turn"},
        ]
    )
    first = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "first", "context_id": context_id},
            },
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["result"]["context_id"] == context_id
    assert first_body["result"]["content"][0]["text"] == "first turn"

    second = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "second", "context_id": context_id},
            },
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["result"]["context_id"] == context_id
    assert second_body["result"]["content"][0]["text"] == "second turn"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_e2e_platform_mcp_audit_events(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    auth_token: str,
    frontend_container,
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_example_react_flow(flows_client_http, auth_headers, unique_id)
    company_id = company_id_from_auth_token(auth_token)
    await mock_llm_with_queue([{"type": "text", "content": "audit trail"}])
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "write audit"},
            },
        },
    )
    assert response.status_code == 200
    assert "result" in response.json()
    await assert_audit_event_in_redis(
        frontend_container,
        company_id=company_id,
        event_type="agent.platform_mcp.tools_call",
    )
