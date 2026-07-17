"""Platform MCP фильтрация по AgentToolkit."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient

from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.models.flow_config import FlowConfig
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from tests.agent._helpers import (
    PLATFORM_MCP_PATH,
    company_id_from_auth_token,
    user_id_from_auth_token,
)


@asynccontextmanager
async def _repository_context_for_auth(
    auth_headers: dict[str, str],
    frontend_container,
) -> AsyncIterator[None]:
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
    *,
    toolkit_id: str | None = None,
) -> list[dict[str, object]]:
    path = PLATFORM_MCP_PATH if toolkit_id is None else f"{PLATFORM_MCP_PATH}/{toolkit_id}"
    response = await flows_client.post(
        path,
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


def _tool_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }


@pytest.mark.asyncio
async def test_platform_mcp_tools_list_scoped_by_toolkit(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_{unique_id}"
    flow_in = f"flow_in_{unique_id}"
    flow_out = f"flow_out_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Test toolkit",
                description="Scoped toolkit",
                default_enabled=False,
                position=1,
                flow_ids=[flow_in],
                tool_ids=[],
                source="custom",
            )
        )
        for flow_id in (flow_in, flow_out):
            await container.flow_repository.set(
                FlowConfig(
                    flow_id=flow_id,
                    name=flow_id,
                    entry="main",
                    nodes={"main": _minimal_llm_node()},
                )
            )
        try:
            scoped = await _mcp_tools_list(flows_client, auth_headers, toolkit_id=toolkit_id)
            scoped_names = {str(tool["name"]) for tool in scoped}
            assert scoped_names == {f"flow_{flow_in}"}

            all_tools = await _mcp_tools_list(flows_client, auth_headers)
            all_names = {str(tool["name"]) for tool in all_tools}
            assert f"flow_{flow_in}" in all_names
            assert f"flow_{flow_out}" not in all_names
        finally:
            await container.flow_repository.delete(flow_in)
            await container.flow_repository.delete(flow_out)
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_platform_mcp_tools_call_rejects_flow_outside_toolkit(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_call_{unique_id}"
    hidden_flow = f"hidden_flow_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Empty toolkit",
                description="No flows",
                flow_ids=[],
                tool_ids=[],
                source="custom",
            )
        )
        await container.flow_repository.set(
            FlowConfig(
                flow_id=hidden_flow,
                name=hidden_flow,
                entry="main",
                nodes={"main": _minimal_llm_node()},
            )
        )
        try:
            response = await flows_client.post(
                f"{PLATFORM_MCP_PATH}/{toolkit_id}",
                headers=auth_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": f"flow_{hidden_flow}",
                        "arguments": {"message": "hello"},
                    },
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert "error" in body
            assert body["error"]["code"] == -32602
        finally:
            await container.flow_repository.delete(hidden_flow)
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_flow_api_persists_agent_toolkit_ids(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    flow_id = f"flow_tk_api_{unique_id}"
    toolkit_id = f"tk_api_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="API toolkit",
                description="For API test",
                flow_ids=[],
                tool_ids=[],
                source="custom",
            )
        )
        try:
            create = await flows_client.post(
                "/flows/api/v1/flows/",
                headers=auth_headers,
                json={
                    "flow_id": flow_id,
                    "name": flow_id,
                    "entry": "main",
                    "nodes": {"main": _minimal_llm_node()},
                    "edges": [{"from_node": "main", "to_node": None}],
                    "agent_toolkit_ids": [toolkit_id],
                },
            )
            assert create.status_code == 200, create.text
            assert create.json()["agent_toolkit_ids"] == [toolkit_id]

            toolkit = await container.agent_toolkit_repository.get(toolkit_id)
            assert toolkit is not None
            assert flow_id in toolkit.flow_ids
        finally:
            await flows_client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers)
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_tool_api_persists_agent_toolkit_ids(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    tool_id = f"tool_tk_api_{unique_id}"
    toolkit_id = f"tk_tool_api_{unique_id}"
    schema = _tool_schema()
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Tool API toolkit",
                description="For tool API test",
                flow_ids=[],
                tool_ids=[],
                source="custom",
            )
        )
        try:
            create = await flows_client.post(
                "/flows/api/v1/tools/",
                headers=auth_headers,
                json={
                    "tool_id": tool_id,
                    "title": tool_id,
                    "code": "async def run(args, state):\n    return 'ok'\n",
                    "parameters_schema": schema,
                    "agent_toolkit_ids": [toolkit_id],
                },
            )
            assert create.status_code == 200, create.text
            assert create.json()["agent_toolkit_ids"] == [toolkit_id]

            toolkit = await container.agent_toolkit_repository.get(toolkit_id)
            assert toolkit is not None
            assert tool_id in toolkit.tool_ids
        finally:
            await flows_client.delete(f"/flows/api/v1/tools/{tool_id}", headers=auth_headers)
            await container.agent_toolkit_repository.delete(toolkit_id)


async def _mcp_jsonrpc(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    method: str,
    toolkit_id: str | None = None,
    params: dict[str, object] | None = None,
    rpc_id: int = 1,
) -> dict[str, object]:
    path = PLATFORM_MCP_PATH if toolkit_id is None else f"{PLATFORM_MCP_PATH}/{toolkit_id}"
    payload: dict[str, object] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = await flows_client.post(path, headers=auth_headers, json=payload)
    return {"status_code": response.status_code, "body": response.json()}


@pytest.mark.asyncio
async def test_platform_mcp_discover_toolkit_server_info(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_disc_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Discover Name",
                description="Discover",
                source="custom",
            )
        )
        try:
            response = await flows_client.get(
                f"{PLATFORM_MCP_PATH}/{toolkit_id}",
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["serverInfo"]["name"] == "Discover Name"

            missing = await flows_client.get(
                f"{PLATFORM_MCP_PATH}/missing_{unique_id}",
                headers=auth_headers,
            )
            assert missing.status_code == 404
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_platform_mcp_initialize_toolkit_server_info(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_init_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Init Name",
                description="Init",
                source="custom",
            )
        )
        try:
            result = await _mcp_jsonrpc(
                flows_client,
                auth_headers,
                method="initialize",
                toolkit_id=toolkit_id,
                params={"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test"}},
            )
            assert result["status_code"] == 200
            body = result["body"]
            assert isinstance(body, dict)
            assert body["result"]["serverInfo"]["name"] == "Init Name"
            assert "instructions" not in body["result"]
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_platform_mcp_initialize_lara_instructions(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
) -> None:
    """LaraOnly: /platform-mcp/lara initialize must instruct Goose to call flow_lara."""
    async with _repository_context_for_auth(auth_headers, frontend_container):
        existing = await container.agent_toolkit_repository.get("lara")
        if existing is None:
            await container.agent_toolkit_repository.set(
                AgentToolkit(
                    toolkit_id="lara",
                    name="Lara",
                    description="Lara",
                    default_enabled=True,
                    position=0,
                    flow_ids=["lara"],
                    source="platform",
                )
            )

    result = await _mcp_jsonrpc(
        flows_client,
        auth_headers,
        method="initialize",
        toolkit_id="lara",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test"},
        },
    )
    assert result["status_code"] == 200
    body = result["body"]
    assert isinstance(body, dict)
    instructions = body["result"]["instructions"]
    assert isinstance(instructions, str)
    assert "flow_lara" in instructions
    assert "NetWorkle" in instructions
    assert body["result"]["serverInfo"]["name"] == "Lara"


@pytest.mark.asyncio
async def test_platform_mcp_scoped_tools_list_includes_builtin_tools(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_tools_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Tools toolkit",
                description="Tools",
                tool_ids=["calculator"],
                source="custom",
            )
        )
        try:
            tools = await _mcp_tools_list(flows_client, auth_headers, toolkit_id=toolkit_id)
            tool_names = {str(tool["name"]) for tool in tools}
            assert any(name.startswith("tool_calculator") for name in tool_names)
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_platform_mcp_builtin_tool_call_in_toolkit(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_id = f"tk_calc_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Calculator toolkit",
                description="Calculator",
                tool_ids=["calculator"],
                source="custom",
            )
        )
        try:
            tools = await _mcp_tools_list(flows_client, auth_headers, toolkit_id=toolkit_id)
            calc_name = next(
                str(tool["name"]) for tool in tools if str(tool["name"]).startswith("tool_calculator")
            )
            result = await _mcp_jsonrpc(
                flows_client,
                auth_headers,
                method="tools/call",
                toolkit_id=toolkit_id,
                params={
                    "name": calc_name,
                    "arguments": {"expression": "2+2"},
                },
                rpc_id=3,
            )
            assert result["status_code"] == 200
            body = result["body"]
            assert isinstance(body, dict)
            assert "result" in body
            content = body["result"]["content"]
            assert isinstance(content, list)
            assert "4" in str(content[0]["text"])
        finally:
            await container.agent_toolkit_repository.delete(toolkit_id)


@pytest.mark.asyncio
async def test_platform_mcp_union_root_lists_all_toolkits(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    toolkit_a = f"tk_union_a_{unique_id}"
    toolkit_b = f"tk_union_b_{unique_id}"
    flow_id = f"flow_union_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_a,
                name="Union A",
                description="A",
                flow_ids=[flow_id],
                source="custom",
            )
        )
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_b,
                name="Union B",
                description="B",
                tool_ids=["calculator"],
                source="custom",
            )
        )
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name=flow_id,
                entry="main",
                nodes={"main": _minimal_llm_node()},
            )
        )
        try:
            tools = await _mcp_tools_list(flows_client, auth_headers)
            names = {str(tool["name"]) for tool in tools}
            assert f"flow_{flow_id}" in names
            assert any(name.startswith("tool_calculator") for name in names)
        finally:
            await container.flow_repository.delete(flow_id)
            await container.agent_toolkit_repository.delete(toolkit_a)
            await container.agent_toolkit_repository.delete(toolkit_b)


@pytest.mark.asyncio
async def test_platform_mcp_flow_in_two_toolkits_visible_in_both(
    flows_client: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    flow_id = f"flow_multi_{unique_id}"
    toolkit_a = f"tk_multi_a_{unique_id}"
    toolkit_b = f"tk_multi_b_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name=flow_id,
                entry="main",
                nodes={"main": _minimal_llm_node()},
            )
        )
        for toolkit_id in (toolkit_a, toolkit_b):
            await container.agent_toolkit_repository.set(
                AgentToolkit(
                    toolkit_id=toolkit_id,
                    name=toolkit_id,
                    description=toolkit_id,
                    flow_ids=[flow_id],
                    source="custom",
                )
            )
        try:
            for toolkit_id in (toolkit_a, toolkit_b):
                tools = await _mcp_tools_list(flows_client, auth_headers, toolkit_id=toolkit_id)
                names = {str(tool["name"]) for tool in tools}
                assert f"flow_{flow_id}" in names
        finally:
            await container.flow_repository.delete(flow_id)
            await container.agent_toolkit_repository.delete(toolkit_a)
            await container.agent_toolkit_repository.delete(toolkit_b)


@pytest.mark.asyncio
async def test_platform_mcp_scoped_endpoint_device_jwt(
    flows_client: AsyncClient,
    frontend_client_with_auth: AsyncClient,
    auth_headers: dict[str, str],
    container,
    frontend_container,
    unique_id: str,
) -> None:
    from tests.agent._helpers import AGENT_API_PREFIX
    from tests.agent.test_platform_mcp_exposure import _repository_context_for_auth

    toolkit_id = f"tk_devjwt_{unique_id}"
    async with _repository_context_for_auth(auth_headers, frontend_container):
        await container.agent_toolkit_repository.set(
            AgentToolkit(
                toolkit_id=toolkit_id,
                name="Device JWT toolkit",
                description="Device JWT",
                tool_ids=["calculator"],
                source="custom",
            )
        )
    pairing = await frontend_client_with_auth.post(f"{AGENT_API_PREFIX}/pairing")
    assert pairing.status_code == 200, pairing.text
    register = await frontend_client_with_auth.post(
        f"{AGENT_API_PREFIX}/register",
        json={
            "pairing_code": pairing.json()["pairing_code"],
            "device_id": f"device_mcp_{unique_id}",
            "device_name": f"Device {unique_id}",
            "os": "darwin",
            "hostname": f"host-{unique_id}",
        },
    )
    assert register.status_code == 200, register.text
    device_token = register.json()["token"]
    try:
        response = await flows_client.post(
            f"{PLATFORM_MCP_PATH}/{toolkit_id}",
            headers={"Authorization": f"Bearer {device_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 200, response.text
        tools = response.json()["result"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) >= 1
    finally:
        async with _repository_context_for_auth(auth_headers, frontend_container):
            await container.agent_toolkit_repository.delete(toolkit_id)
