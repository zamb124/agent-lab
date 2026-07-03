"""Bundle humanitec_agent: exposed_to_agent и curated tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.services.flows_loader import FlowsLoader


@pytest.fixture
def bundles_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "apps" / "flows" / "bundles"


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
async def test_humanitec_agent_bundle_exposed_to_agent(loader: FlowsLoader) -> None:
    flow_config = await loader.build_flow_bundle_config("humanitec_agent")
    assert flow_config is not None
    assert flow_config.flow_id == "humanitec_agent"
    assert flow_config.exposed_to_agent is True


@pytest.mark.asyncio
async def test_humanitec_agent_bundle_curated_tools(loader: FlowsLoader) -> None:
    flow_config = await loader.build_flow_bundle_config("humanitec_agent")
    assert flow_config is not None
    main_node = flow_config.nodes["main"]
    assert isinstance(main_node, dict)
    tools_raw = main_node.get("tools")
    assert isinstance(tools_raw, list)
    tool_ids = [str(item) for item in tools_raw]
    assert "rag_search" in tool_ids
    assert "ask_user" in tool_ids
    assert "calculator" not in tool_ids


def test_flow_config_exposed_to_agent_defaults_false() -> None:
    from apps.flows.src.models.flow_config import FlowConfig

    flow_config = FlowConfig.model_validate(
        {
            "flow_id": "legacy_flow",
            "name": "Legacy",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "x"}},
        }
    )
    assert flow_config.exposed_to_agent is False
