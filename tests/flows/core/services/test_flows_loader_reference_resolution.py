"""Demand-driven резолв tool refs в FlowsLoader при доминировании MCP-каталога."""

from __future__ import annotations

from pathlib import Path
from typing import Never

import pytest

from apps.flows.src.models import ToolReference
from apps.flows.src.models.enums import CodeMode
from apps.flows.src.services.flows_loader import FlowsLoader, load_tools_to_db
from core.integrations.mcp import mcp_parameters_schema_hash, mcp_tool_reference_id
from core.types import JsonObject


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


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


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_build_example_react_resolves_calculator_without_bulk_tool_list(
    app, unique_id: str, monkeypatch: pytest.MonkeyPatch,
    di,
) -> None:
    """
    Регрессия prod: сборка bundle не должна вызывать ToolReference.list;
    calculator резолвится через get_many по явным ID.
    """
    _ = app
    _ = await load_tools_to_db(
        flow_access_service=di.flow_access_service,
    )

    calculator = await ToolReference.get(ToolReference.row_id_for_active_company("calculator"))
    assert calculator is not None

    server_id = f"loader_mcp_flood_{unique_id}"
    for index in range(250):
        _ = await ToolReference.set(
            _mcp_tool_reference(server_id, f"flood_tool_{index}")
        )

    async def _list_must_not_be_called(*_args: object, **_kwargs: object) -> Never:
        raise AssertionError(
            "FlowsLoader must not bulk-load tools via ToolReference.list; use get_many by ID"
        )

    monkeypatch.setattr(ToolReference, "list", _list_must_not_be_called)

    bundles_dir = _repo_root() / "apps" / "flows" / "bundles"
    registry_path = _repo_root() / "apps" / "flows" / "registry.yaml"
    loader = FlowsLoader(
        bundles_dir=bundles_dir,
        registry_path=registry_path,
        flow_access_service=di.flow_access_service,
    )
    loader._target_company_id = "system"

    flow_config = await loader.build_flow_bundle_config("example_react")
    assert flow_config is not None
    assert flow_config.nodes is not None

    main_node = flow_config.nodes["main"]
    assert isinstance(main_node, dict)
    tools_raw = main_node.get("tools")
    assert isinstance(tools_raw, list)

    tool_ids = [
        item["tool_id"] for item in tools_raw if isinstance(item, dict) and "tool_id" in item
    ]
    assert "calculator" in tool_ids
