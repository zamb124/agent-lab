"""Picker category filters for GET /flows/api/v1/tools/all."""

import pytest

from apps.flows.src.models import Edge, FlowConfig, ToolReference
from apps.flows.src.models.enums import CodeMode
from core.context import require_active_company, require_context
from core.integrations.mcp import mcp_parameters_schema_hash, mcp_tool_reference_id
from core.types import JsonObject

_TOOLS_ALL_PAGE = 20
_MCP_OVERFLOW = _TOOLS_ALL_PAGE + 5


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


async def _persist_tool(container, tool: ToolReference) -> None:
    await container.tool_repository.set(tool)
    await container.flow_access_service.sync_tool_saved(
        tool.tool_id,
        company_id=require_active_company().company_id,
        permission=[],
    )


async def _persist_flow(container, config: FlowConfig) -> None:
    await container.flow_repository.set(config)
    await container.flow_access_service.sync_flow_saved(
        config,
        company_id=require_active_company().company_id,
        owner_user_id=require_context().user.user_id,
    )


async def _get_tools_all(
    client,
    *,
    picker_category: str,
    q: str,
) -> dict:
    path = (
        f"/flows/api/v1/tools/all?limit={_TOOLS_ALL_PAGE}&offset=0"
        f"&picker_category={picker_category}&q={q}"
    )
    response = await client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    return body


@pytest.mark.asyncio
async def test_tools_all_rejects_limit_above_page_max(client, app):
    response = await client.get("/flows/api/v1/tools/all?limit=21&offset=0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tools_all_q_filters_before_pagination(client, app, unique_id, container):
    tool_id = f"picker_search_{unique_id}"
    await _persist_tool(container, _inline_tool_reference(tool_id))

    body = await _get_tools_all(client, picker_category="code", q=tool_id)
    ids = {item["tool_id"] for item in body["items"]}
    assert tool_id in ids
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_picker_category_flow_is_not_truncated_by_many_mcp_tools(
    client, app, unique_id, container
):
    """Flows вкладка и picker_category=all сохраняют flow при MCP > page size."""
    flow_id = f"picker_flow_{unique_id}"
    code_tool_id = f"picker_code_{unique_id}"
    server_id = f"picker_mcp_{unique_id}"

    await _persist_flow(container, _flow_config(flow_id))
    await _persist_tool(container, _inline_tool_reference(code_tool_id))
    for index in range(_MCP_OVERFLOW):
        await _persist_tool(container, _mcp_tool_reference(server_id, f"bulk_tool_{index}"))

    flow_body = await _get_tools_all(client, picker_category="flow", q=flow_id)
    flow_ids = {item["tool_id"] for item in flow_body["items"]}
    assert flow_id in flow_ids
    assert all(item.get("item_type") == "flow" for item in flow_body["items"])

    all_body = await _get_tools_all(client, picker_category="all", q=flow_id)
    all_ids = {item["tool_id"] for item in all_body["items"]}
    assert flow_id in all_ids


@pytest.mark.asyncio
async def test_picker_flow_item_contains_complete_flow_tool_schema(
    client, app, unique_id, container
):
    flow_id = f"picker_contract_{unique_id}"
    await _persist_flow(container, _flow_config(flow_id))

    body = await _get_tools_all(client, picker_category="flow", q=flow_id)
    item = next(entry for entry in body["items"] if entry["tool_id"] == flow_id)
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
async def test_picker_category_filters_code_and_mcp(client, app, unique_id, container):
    """picker_category=code и picker_category=mcp возвращают непересекающиеся наборы."""
    code_tool_id = f"picker_inline_{unique_id}"
    server_id = f"picker_mcp_only_{unique_id}"
    mcp_tool_name = "only_mcp_tool"
    mcp_tool_id = mcp_tool_reference_id(server_id, mcp_tool_name)

    await _persist_tool(container, _inline_tool_reference(code_tool_id))
    await _persist_tool(container, _mcp_tool_reference(server_id, mcp_tool_name))

    code_body = await _get_tools_all(client, picker_category="code", q=code_tool_id)
    code_ids = {item["tool_id"] for item in code_body["items"]}
    assert code_tool_id in code_ids
    assert mcp_tool_id not in code_ids
    assert all(item.get("item_type") != "flow" for item in code_body["items"])

    mcp_body = await _get_tools_all(client, picker_category="mcp", q=mcp_tool_id)
    mcp_ids = {item["tool_id"] for item in mcp_body["items"]}
    assert mcp_tool_id in mcp_ids
    assert code_tool_id not in mcp_ids


@pytest.mark.asyncio
async def test_picker_category_all_skips_agent_toolkit_lookup(
    client, app, monkeypatch, unique_id, container
):
    """picker_category=all не вызывает N+1 lookup agent_toolkit_ids."""
    flow_id = f"picker_fast_flow_{unique_id}"
    await _persist_flow(container, _flow_config(flow_id))

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

    body = await _get_tools_all(client, picker_category="all", q=flow_id)
    ids = {item["tool_id"] for item in body["items"]}
    assert flow_id in ids
