"""Platform MCP flow archetype E2E (:9001)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient

from tests.agent._helpers import PLATFORM_MCP_PATH
from tests.agent.fixtures.flow_archetypes import (
    ensure_failed_flow,
    ensure_handoff_parent_child,
    ensure_interrupt_flow,
    ensure_multi_node_flow,
    ensure_react_flow,
    ensure_tool_only_flow,
)


async def _tools_call(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    flow_id: str,
    message: str,
    context_id: str | None = None,
    rpc_id: int = 1,
) -> dict[str, object]:
    arguments: dict[str, str] = {"message": message}
    if context_id is not None:
        arguments["context_id"] = context_id
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": arguments,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("MCP response must be object")
    return body


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_interrupt_and_resume(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_interrupt_flow(flows_client_http, auth_headers, unique_id)
    context_id = f"ctx-interrupt-{unique_id}"
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
            {"type": "text", "content": "Привет, Иван!"},
        ]
    )
    first = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_id,
        message="start",
        context_id=context_id,
        rpc_id=301,
    )
    assert "result" in first
    first_result = first["result"]
    assert isinstance(first_result, dict)
    assert first_result["task_state"] == "input-required"
    assert first_result["context_id"] == context_id
    content = first_result["content"]
    assert isinstance(content, list)
    assert "зовут" in str(content[0]["text"]).lower()

    second = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_id,
        message="Иван",
        context_id=context_id,
        rpc_id=302,
    )
    assert "result" in second
    second_result = second["result"]
    assert isinstance(second_result, dict)
    assert second_result["task_state"] == "completed"
    assert "иван" in str(second_result["content"][0]["text"]).lower()


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_handoff_parent_child(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    parent_fid, child_fid = await ensure_handoff_parent_child(
        flows_client_http,
        auth_headers,
        unique_id,
    )
    await mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {
                    "target_flow_id": child_fid,
                    "variables": {"order_id": "42"},
                    "reason": "test",
                },
            },
            {"type": "text", "content": "Child handled order 42"},
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"summary": "done"}},
            {"type": "text", "content": "Parent final answer"},
        ]
    )
    body = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=parent_fid,
        message="handoff please",
        rpc_id=303,
    )
    assert "result" in body
    result = body["result"]
    assert isinstance(result, dict)
    assert result["task_state"] == "input-required"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_handback_demo(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    from tests.agent.fixtures.flow_archetypes import ensure_handoff_demo_bundles

    parent_fid, child_fid = await ensure_handoff_demo_bundles(
        flows_client_http,
        auth_headers,
    )
    await mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {
                    "target_flow_id": child_fid,
                    "variables": {"order_id": "99", "customer_name": "Test"},
                    "reason": "order issue",
                },
            },
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"summary": "ticket created"}},
            {"type": "text", "content": "Handback complete"},
        ]
    )
    body = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=parent_fid,
        message="проблема с заказом",
        rpc_id=304,
    )
    assert "result" in body


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_tool_calculator(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_tool_only_flow(flows_client_http, auth_headers, unique_id)
    await mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            {"type": "text", "content": "Result is 4"},
        ]
    )
    body = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_id,
        message="calculate 2+2",
        rpc_id=305,
    )
    assert "result" in body
    result = body["result"]
    assert isinstance(result, dict)
    assert result["task_state"] == "completed"


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_multi_node(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_multi_node_flow(flows_client_http, auth_headers, unique_id)
    await mock_llm_with_queue(
        [
            {"type": "text", "content": "first node done"},
            {"type": "text", "content": "second node done"},
        ]
    )
    body = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_id,
        message="run multi",
        rpc_id=306,
    )
    assert "result" in body


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_failed_returns_error(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
) -> None:
    _ = flows_service, flows_worker
    flow_id = await ensure_failed_flow(flows_client_http, auth_headers, unique_id)
    body = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_id,
        message="fail",
        rpc_id=307,
    )
    assert "error" in body
    error = body["error"]
    assert isinstance(error, dict)
    assert error["code"] == -32000


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_flow_two_flows_mapping(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service, flows_worker
    flow_a = await ensure_react_flow(flows_client_http, auth_headers, f"a-{unique_id}")
    flow_b = await ensure_react_flow(flows_client_http, auth_headers, f"b-{unique_id}")
    list_response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 308, "method": "tools/list", "params": {}},
    )
    assert list_response.status_code == 200
    tools = list_response.json()["result"]["tools"]
    tool_names = {tool["name"] for tool in tools if isinstance(tool, dict)}
    assert f"flow_{flow_a}" in tool_names
    assert f"flow_{flow_b}" in tool_names

    await mock_llm_with_queue([{"type": "text", "content": "flow A response"}])
    call_a = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_a,
        message="call A",
        rpc_id=309,
    )
    assert call_a["result"]["content"][0]["text"] == "flow A response"

    await mock_llm_with_queue([{"type": "text", "content": "flow B response"}])
    call_b = await _tools_call(
        flows_client_http,
        auth_headers,
        flow_id=flow_b,
        message="call B",
        rpc_id=310,
    )
    assert call_b["result"]["content"][0]["text"] == "flow B response"


@pytest.mark.asyncio
async def test_mcp_flow_tools_list_description(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    unique_id: str,
) -> None:
    _ = flows_service
    flow_id = await ensure_interrupt_flow(flows_client_http, auth_headers, unique_id)
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 311, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    matched = next(
        (tool for tool in tools if isinstance(tool, dict) and tool.get("name") == f"flow_{flow_id}"),
        None,
    )
    assert matched is not None
    assert isinstance(matched.get("description"), str)
    assert matched["description"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_mcp_parallel_tools_call(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    flows_worker: None,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
    unique_id: str,
) -> None:
    _ = flows_service, flows_worker
    flow_a = await ensure_react_flow(flows_client_http, auth_headers, f"{unique_id}-parallel-a")
    flow_b = await ensure_react_flow(flows_client_http, auth_headers, f"{unique_id}-parallel-b")
    await mock_llm_with_queue(
        [
            {"type": "text", "content": "parallel A"},
            {"type": "text", "content": "parallel B"},
        ]
    )

    async def call_flow(flow_id: str, message: str, rpc_id: int) -> dict[str, object]:
        return await _tools_call(
            flows_client_http,
            auth_headers,
            flow_id=flow_id,
            message=message,
            rpc_id=rpc_id,
        )

    call_a, call_b = await asyncio.gather(
        call_flow(flow_a, "parallel message A", 312),
        call_flow(flow_b, "parallel message B", 313),
    )
    assert call_a["result"]["task_state"] == "completed"
    assert call_b["result"]["task_state"] == "completed"


@pytest.mark.asyncio
async def test_mcp_flow_taskiq_worker_down(
    flows_client_http: AsyncClient,
    auth_headers: dict[str, str],
    flows_service: None,
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], Awaitable[None]],
) -> None:
    _ = flows_service
    flow_id = await ensure_react_flow(flows_client_http, auth_headers, f"worker-down-{unique_id}")
    await mock_llm_with_queue([{"type": "text", "content": "should not run"}])
    response = await flows_client_http.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 320,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "worker down probe"},
            },
        },
    )
    body = response.json()
    if response.status_code == 200 and isinstance(body, dict) and "result" in body:
        task_state = body["result"].get("task_state")
        assert task_state in {"failed", "input-required", "working", "completed"}
        return
    assert response.status_code >= 400 or "error" in body
