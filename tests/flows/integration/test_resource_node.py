"""Интеграционные тесты ноды type=resource (pass-through)."""

import pytest

from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import ResourceNode, create_node
from core.state import ExecutionState


def _minimal_state() -> ExecutionState:
    return ExecutionState(
        task_id="test-task",
        context_id="test-context",
        user_id="test-user",
        session_id="test-flow:test-context",
        messages=[],
    )


class TestResourceNode:
    @pytest.mark.asyncio
    async def test_create_node_registry(self, container) -> None:
        node = await create_node(
            "res_a",
            {"type": NodeType.RESOURCE.value, "resources": {}},
            container=container,
        )
        assert isinstance(node, ResourceNode)
        assert node.node_id == "res_a"

    @pytest.mark.asyncio
    async def test_run_leaves_state_unchanged(self, container) -> None:
        node = ResourceNode(
            node_id="res_b",
            config={"type": NodeType.RESOURCE.value, "resources": {}},
            container=container,
        )
        state = _minimal_state()
        state.content = "keep"
        out = await node.run(state)
        assert out is state
        assert out.content == "keep"
