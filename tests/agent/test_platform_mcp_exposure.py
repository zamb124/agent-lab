"""Строгие тесты фильтрации Platform MCP по exposed_to_agent."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import AsyncClient

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.tools.agent_exposure import DEFAULT_AGENT_TOOL_IDS
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from tests.agent._helpers import (
    PLATFORM_MCP_PATH,
    company_id_from_auth_token,
    ensure_example_react_flow,
    user_id_from_auth_token,
)

@asynccontextmanager
async def _repository_context_for_auth(
    auth_headers: dict[str, str],
    frontend_container,
) -> AsyncIterator[None]:
    """Переключает company context репозиториев на компанию из JWT (не system)."""
    authorization = auth_headers["Authorization"]
    if not authorization.startswith("Bearer "):
        raise AssertionError("expected Bearer auth header")
    auth_token = authorization.removeprefix("Bearer ").strip()
    company_id = company_id_from_auth_token(auth_token)
    user_id = user_id_from_auth_token(auth_token)
    company = await frontend_container.company_repository.get(company_id)
    if company is None:
        raise AssertionError(f"company not found: {company_id}")
    user = await frontend_container.user_repository.get(user_id)
    if user is None:
        raise AssertionError(f"user not found: {user_id}")
    previous = get_context()
    set_context(
        Context(
            user=user,
            active_company=company,
            session_id="test_session",
            channel="test",
            metadata={},
        )
    )
    try:
        yield
    finally:
        clear_context()
        if previous is not None:
            set_context(previous)


async def _mcp_tools_list(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> list[dict[str, object]]:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    tools_raw = body["result"]["tools"]
    assert isinstance(tools_raw, list)
    return [tool for tool in tools_raw if isinstance(tool, dict)]


def _minimal_llm_node() -> dict[str, object]:
    return {
        "type": "llm_node",
        "prompt": "Reply briefly.",
        "llm": {"provider": "mock", "model": "mock-gpt-4"},
    }


@pytest.mark.asyncio
async def test_platform_mcp_tools_list_only_exposed_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    exposed_id = f"exposed_flow_{unique_id}"
    hidden_id = f"hidden_flow_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        for flow_id, exposed in ((exposed_id, True), (hidden_id, False)):
            await container.flow_repository.set(
                FlowConfig(
                    flow_id=flow_id,
                    name=flow_id,
                    entry="main",
                    nodes={"main": _minimal_llm_node()},
                    exposed_to_agent=exposed,
                )
            )
        try:
            tools = await _mcp_tools_list(flows_client, auth_headers)
            names = {str(tool["name"]) for tool in tools}
            assert f"flow_{exposed_id}" in names
            assert f"flow_{hidden_id}" not in names
        finally:
            await container.flow_repository.delete(exposed_id)
            await container.flow_repository.delete(hidden_id)


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_rejects_non_exposed_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    flow_id = f"private_flow_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name=flow_id,
                entry="main",
                nodes={"main": _minimal_llm_node()},
                exposed_to_agent=False,
            )
        )
        try:
            response = await flows_client.post(
                PLATFORM_MCP_PATH,
                headers=auth_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{flow_id}",
                        "arguments": {"message": "hello"},
                    },
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["error"]["code"] == -32602
            assert "HumanitecAgent" in body["error"]["message"]
        finally:
            await container.flow_repository.delete(flow_id)


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_exposed_flow(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
    mock_llm_with_queue: Callable[[list[Any]], object],
) -> None:
    flow_id = await ensure_example_react_flow(flows_client, auth_headers, unique_id)
    mock_llm_with_queue([{"type": "text", "content": "exposure ok"}])
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": f"flow_{flow_id}",
                "arguments": {"message": "ping"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert body["result"]["content"][0]["text"] == "exposure ok"


@pytest.mark.asyncio
async def test_platform_mcp_builtin_tools_curated_only(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    tools = await _mcp_tools_list(flows_client, auth_headers)
    catalog_names = {str(tool["name"]) for tool in tools if str(tool["name"]).startswith("tool_")}
    for tool_id in DEFAULT_AGENT_TOOL_IDS:
        assert f"tool_{tool_id}" in catalog_names
    assert "tool_calculator" not in catalog_names


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_rejects_non_default_builtin(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await flows_client.post(
        PLATFORM_MCP_PATH,
        headers=auth_headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "tool_calculator",
                "arguments": {"expression": "1+1"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_platform_mcp_custom_tool_exposure(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    exposed_id = f"exposed_tool_{unique_id}"
    hidden_id = f"hidden_tool_{unique_id}"
    schema: dict[str, object] = {"type": "object", "properties": {}}
    async with _repository_context_for_auth(auth_headers, frontend_container):
        for tool_id, exposed in ((exposed_id, True), (hidden_id, False)):
            await container.tool_repository.set(
                ToolReference(
                    tool_id=tool_id,
                    title=tool_id,
                    description="test",
                    parameters_schema=schema,
                    code="async def run(args, state):\n    return 'ok'\n",
                    exposed_to_agent=exposed,
                )
            )
        try:
            tools = await _mcp_tools_list(flows_client, auth_headers)
            names = {str(tool["name"]) for tool in tools}
            assert f"tool_{exposed_id}" in names
            assert f"tool_{hidden_id}" not in names
        finally:
            await container.tool_repository.delete(exposed_id)
            await container.tool_repository.delete(hidden_id)


@pytest.mark.asyncio
async def test_platform_mcp_list_stays_small_with_many_entities(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    exposed_flow_id = f"humanitec_seed_{unique_id}"
    seeded_flow_ids: list[str] = []
    seeded_tool_ids: list[str] = []

    async with _repository_context_for_auth(auth_headers, frontend_container):
        existing_flows = await container.flow_repository.list(limit=10000)
        for flow_row in existing_flows:
            if flow_row.exposed_to_agent:
                flow_row.exposed_to_agent = False
                await container.flow_repository.set(flow_row)

        await container.flow_repository.set(
            FlowConfig(
                flow_id=exposed_flow_id,
                name="Humanitec seed",
                entry="main",
                nodes={"main": _minimal_llm_node()},
                exposed_to_agent=True,
            )
        )
        seeded_flow_ids.append(exposed_flow_id)

        for index in range(30):
            flow_id = f"bulk_flow_{unique_id}_{index}"
            await container.flow_repository.set(
                FlowConfig(
                    flow_id=flow_id,
                    name=flow_id,
                    entry="main",
                    nodes={"main": _minimal_llm_node()},
                    exposed_to_agent=False,
                )
            )
            seeded_flow_ids.append(flow_id)

        schema: dict[str, object] = {"type": "object", "properties": {}}
        for index in range(100):
            tool_id = f"bulk_tool_{unique_id}_{index}"
            await container.tool_repository.set(
                ToolReference(
                    tool_id=tool_id,
                    title=tool_id,
                    description="bulk",
                    parameters_schema=schema,
                    code="async def run(args, state):\n    return 'ok'\n",
                    exposed_to_agent=False,
                )
            )
            seeded_tool_ids.append(tool_id)

        try:
            tools = await _mcp_tools_list(flows_client, auth_headers)
            expected_max = len(DEFAULT_AGENT_TOOL_IDS) + 1
            assert len(tools) == expected_max
            assert len(tools) < 50
            names = {str(tool["name"]) for tool in tools}
            assert f"flow_{exposed_flow_id}" in names
            assert all(not name.startswith("flow_bulk_flow_") for name in names)
            assert all(not name.startswith("tool_bulk_tool_") for name in names)
        finally:
            for flow_id in seeded_flow_ids:
                await container.flow_repository.delete(flow_id)
            for tool_id in seeded_tool_ids:
                await container.tool_repository.delete(tool_id)


@pytest.mark.asyncio
async def test_flow_api_persists_exposed_to_agent(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    flow_id = f"api_exposed_{unique_id}"
    create = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers,
        json={
            "flow_id": flow_id,
            "name": "API exposed",
            "entry": "main",
            "nodes": {"main": _minimal_llm_node()},
            "edges": [{"from_node": "main", "to_node": None}],
            "exposed_to_agent": True,
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["exposed_to_agent"] is True

    get_resp = await flows_client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["exposed_to_agent"] is True

    update = await flows_client.put(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers,
        json={
            "flow_id": flow_id,
            "name": "API exposed off",
            "entry": "main",
            "nodes": {"main": _minimal_llm_node()},
            "edges": [{"from_node": "main", "to_node": None}],
            "exposed_to_agent": False,
        },
    )
    assert update.status_code == 200
    assert update.json()["exposed_to_agent"] is False

    await flows_client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_tool_api_persists_exposed_to_agent(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    unique_id: str,
) -> None:
    tool_id = f"api_tool_{unique_id}"
    schema: dict[str, object] = {"type": "object", "properties": {}}
    create = await flows_client.post(
        "/flows/api/v1/tools/",
        headers=auth_headers,
        json={
            "tool_id": tool_id,
            "title": tool_id,
            "description": "test",
            "code": "async def run(args, state):\n    return 'ok'\n",
            "parameters_schema": schema,
            "exposed_to_agent": True,
        },
    )
    assert create.status_code == 200, create.text
    assert create.json()["exposed_to_agent"] is True

    get_resp = await flows_client.get(f"/flows/api/v1/tools/{tool_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["exposed_to_agent"] is True

    await flows_client.delete(f"/flows/api/v1/tools/{tool_id}", headers=auth_headers)
