"""Picker category filters for GET /flows/api/v1/tools/all."""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import Edge, FlowConfig, ToolReference
from apps.flows.src.models.enums import CodeMode
from core.integrations.mcp import mcp_parameters_schema_hash, mcp_tool_reference_id
from core.types import JsonObject


def _empty_parameters_schema() -> JsonObject:
    return {
        "type": "object",
        "properties": {},
        "required": [],
    }


def _mcp_tool_reference(server_id: str, tool_name: str) -> ToolReference:
    parameters_schema = _empty_parameters_schema()
    return ToolReference(
        tool_id=mcp_tool_reference_id(server_id, tool_name),
        title=tool_name,
        description=f"MCP tool {tool_name}",
        code_mode=CodeMode.MCP_TOOL,
        mcp_server_id=server_id,
        mcp_tool_name=tool_name,
        mcp_schema_hash=mcp_parameters_schema_hash(parameters_schema),
        mcp_schema_version="1",
        parameters_schema=parameters_schema,
    )


def _inline_tool_reference(tool_id: str) -> ToolReference:
    return ToolReference(
        tool_id=tool_id,
        title=tool_id,
        description=f"Inline tool {tool_id}",
        code="async def run(args, state):\n    return args",
        parameters_schema=_empty_parameters_schema(),
    )


def _flow_config(flow_id: str) -> FlowConfig:
    return FlowConfig(
        flow_id=flow_id,
        name=f"Flow {flow_id}",
        description=f"Picker flow {flow_id}",
        entry="main",
        nodes={"main": {"type": "code", "code": "async def run(args, state):\n    return state"}},
        edges=[Edge(from_node="main", to_node=None)],
    )


@pytest.mark.asyncio
async def test_picker_category_flow_is_not_truncated_by_many_mcp_tools(client, app, unique_id):
    """Flows вкладка и picker_category=all сохраняют flow при большом числе MCP tools."""
    container = get_container()
    flow_id = f"picker_flow_{unique_id}"
    code_tool_id = f"picker_code_{unique_id}"
    server_id = f"picker_mcp_{unique_id}"

    await container.flow_repository.set(_flow_config(flow_id))
    await container.tool_repository.set(_inline_tool_reference(code_tool_id))
    for index in range(120):
        await container.tool_repository.set(
            _mcp_tool_reference(server_id, f"bulk_tool_{index}")
        )

    flow_response = await client.get(
        "/flows/api/v1/tools/all?picker_category=flow&limit=2000&offset=0"
    )
    assert flow_response.status_code == 200
    flow_ids = {item["tool_id"] for item in flow_response.json()["items"]}
    assert flow_id in flow_ids

    all_response = await client.get(
        "/flows/api/v1/tools/all?picker_category=all&limit=2000&offset=0"
    )
    assert all_response.status_code == 200
    all_ids = {item["tool_id"] for item in all_response.json()["items"]}
    assert flow_id in all_ids


@pytest.mark.asyncio
async def test_picker_flow_item_contains_complete_flow_tool_schema(client, app, unique_id):
    container = get_container()
    flow_id = f"picker_contract_{unique_id}"
    await container.flow_repository.set(_flow_config(flow_id))

    response = await client.get(
        "/flows/api/v1/tools/all?picker_category=flow&limit=2000&offset=0"
    )

    assert response.status_code == 200
    item = next(entry for entry in response.json()["items"] if entry["tool_id"] == flow_id)
    assert item["item_type"] == "flow"
    assert item["parameters_schema"] == {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "Запрос, передаваемый дочернему flow",
            }
        },
        "required": ["request"],
        "additionalProperties": False,
    }


@pytest.mark.asyncio
async def test_picker_category_filters_code_and_mcp(client, app, unique_id):
    """picker_category=code и picker_category=mcp возвращают непересекающиеся наборы."""
    container = get_container()
    code_tool_id = f"picker_inline_{unique_id}"
    server_id = f"picker_mcp_only_{unique_id}"
    mcp_tool_name = "only_mcp_tool"

    await container.tool_repository.set(_inline_tool_reference(code_tool_id))
    await container.tool_repository.set(_mcp_tool_reference(server_id, mcp_tool_name))

    code_response = await client.get(
        "/flows/api/v1/tools/all?picker_category=code&limit=2000&offset=0"
    )
    assert code_response.status_code == 200
    code_items = code_response.json()["items"]
    code_ids = {item["tool_id"] for item in code_items}
    assert code_tool_id in code_ids
    assert mcp_tool_reference_id(server_id, mcp_tool_name) not in code_ids
    assert all(item.get("item_type") != "flow" for item in code_items)

    mcp_response = await client.get(
        "/flows/api/v1/tools/all?picker_category=mcp&limit=2000&offset=0"
    )
    assert mcp_response.status_code == 200
    mcp_ids = {item["tool_id"] for item in mcp_response.json()["items"]}
    assert mcp_tool_reference_id(server_id, mcp_tool_name) in mcp_ids
    assert code_tool_id not in mcp_ids


@pytest.mark.asyncio
async def test_picker_category_all_skips_agent_toolkit_lookup(client, app, monkeypatch, unique_id):
    """picker_category=all не вызывает N+1 lookup agent_toolkit_ids."""
    container = get_container()
    flow_id = f"picker_fast_flow_{unique_id}"
    await container.flow_repository.set(_flow_config(flow_id))

    async def _fail_toolkit_lookup(*_args, **_kwargs):
        raise AssertionError("picker endpoint must not resolve agent_toolkit_ids")

    monkeypatch.setattr(
        "apps.flows.src.api.v1.tools._toolkit_ids_for_tool",
        _fail_toolkit_lookup,
    )
    monkeypatch.setattr(
        "apps.flows.src.api.v1.tools._toolkit_ids_for_flow",
        _fail_toolkit_lookup,
    )

    response = await client.get(
        "/flows/api/v1/tools/all?picker_category=all&limit=2000&offset=0"
    )
    assert response.status_code == 200
    ids = {item["tool_id"] for item in response.json()["items"]}
    assert flow_id in ids
