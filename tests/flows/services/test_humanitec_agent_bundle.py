"""Registry agent_toolkits bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.services.agent_toolkit_service import bootstrap_agent_toolkits_from_registry
from apps.flows.src.services.flows_loader import FlowsLoader


@pytest.fixture
def bundles_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "apps" / "flows" / "bundles"


@pytest.fixture
def registry_path(bundles_dir: Path) -> Path:
    return bundles_dir.parent / "registry.yaml"


@pytest.fixture
def loader(bundles_dir: Path, container) -> FlowsLoader:
    return FlowsLoader(
        bundles_dir=bundles_dir,
        flow_repository=container.flow_repository,
        node_repository=container.node_repository,
        tool_repository=container.tool_repository,
        registry_path=bundles_dir.parent / "registry.yaml",
    )


@pytest.mark.asyncio
async def test_registry_defines_humanitec_core_toolkit(registry_path: Path, container) -> None:
    loaded = await bootstrap_agent_toolkits_from_registry(
        container.agent_toolkit_repository,
        registry_path,
        filter_public=False,
    )
    assert loaded >= 1
    toolkit = await container.agent_toolkit_repository.get("humanitec_core")
    assert toolkit is not None
    assert "humanitec_agent" in toolkit.flow_ids
    assert toolkit.default_enabled is True


@pytest.mark.asyncio
async def test_humanitec_agent_bundle_exists(loader: FlowsLoader) -> None:
    flow_config = await loader.build_flow_bundle_config("humanitec_agent")
    assert flow_config is not None
    assert flow_config.flow_id == "humanitec_agent"


@pytest.mark.asyncio
async def test_humanitec_agent_bundle_curated_tools(loader: FlowsLoader) -> None:
    flow_config = await loader.build_flow_bundle_config("humanitec_agent")
    assert flow_config is not None
    main_node = flow_config.nodes["main"]
    assert isinstance(main_node, dict)
    tools_raw = main_node.get("tools")
    assert isinstance(tools_raw, list)
    tool_ids = [item["tool_id"] for item in tools_raw]
    assert "rag_search" in tool_ids
    assert "ask_user" in tool_ids
    assert "calculator" not in tool_ids


def test_agent_toolkit_model() -> None:
    toolkit = AgentToolkit(
        toolkit_id="networkle",
        name="NetWorkle",
        description="CRM tools",
        flow_ids=[],
        tool_ids=["crm_search_entities"],
    )
    assert toolkit.toolkit_id == "networkle"
    assert toolkit.source == "platform"
