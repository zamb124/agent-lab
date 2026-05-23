from __future__ import annotations

import pytest

from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig


def test_llm_node_context_config_is_a_simple_strict_patch() -> None:
    node = NodeConfig(
        node_id="agent",
        type=NodeType.LLM_NODE,
        name="Agent",
        prompt="Answer briefly",
        llm_context={"profile": "agent", "memory": "node"},
        llm_context_resource_key="ctx",
    )

    assert node.llm_context is not None
    assert node.llm_context.profile == "agent"
    assert node.llm_context.memory == "node"
    assert node.model_dump(exclude_none=True)["llm_context"] == {
        "profile": "agent",
        "memory": "node",
    }
    assert node.llm_context_resource_key == "ctx"


def test_resource_node_rejects_llm_context_surface() -> None:
    with pytest.raises(ValueError, match="llm_context"):
        NodeConfig(
            node_id="resource",
            type=NodeType.RESOURCE,
            name="Resource",
            llm_context={"profile": "compact"},
        )
