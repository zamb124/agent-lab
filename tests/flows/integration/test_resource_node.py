"""Интеграционные тесты ноды type=resource (pass-through)."""

import uuid

import pytest

from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import ResourceNode, create_node
from apps.flows.src.state import ExecutionState


def _minimal_state() -> ExecutionState:
    uid = uuid.uuid4().hex[:12]
    return ExecutionState(
        task_id=f"test-task-{uid}",
        context_id=f"test-context-{uid}",
        user_id="test-user",
        session_id=f"test-flow:test-context-{uid}",
        messages=[],
    )


class TestResourceNode:
    @pytest.mark.asyncio
    async def test_create_node_registry(self, di) -> None:
        node = await create_node(
            "res_a",
            {"type": NodeType.RESOURCE.value, "resources": {}},
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )
        assert isinstance(node, ResourceNode)
        assert node.node_id == "res_a"

    @pytest.mark.asyncio
    async def test_run_leaves_state_unchanged(self, di) -> None:
        node = ResourceNode(
            node_id="res_b",
            config={"type": NodeType.RESOURCE.value, "resources": {}},
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client,
        )
        state = _minimal_state()
        state.content = "keep"
        out = await node.run(state)
        assert out is state
        assert out.content == "keep"
