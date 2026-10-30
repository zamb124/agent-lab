from __future__ import annotations

import pytest

from apps.flows.src.flow_ui.templates import default_chat_document
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, CodeNode, NodeInputs, NodeRunResult, create_node
from apps.flows.src.state import ExecutionState
from apps.flows.src.streaming.emitter import EmitterFactory
from core.clients.redis_client import RedisClient


class _NoWorkflowRuntime:
    async def get_active_execution_position(self, session_id: str) -> None:
        _ = session_id
        return None


class _PureNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = state
        _ = inputs
        return None


def _state() -> ExecutionState:
    return ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="strict_flow:ctx",
    )


@pytest.mark.asyncio
async def test_flow_from_config_requires_node_constructor() -> None:
    with pytest.raises(TypeError, match="node_constructor"):
        _ = await Flow.from_config(
            {
                "flow_id": "strict_flow",
                "name": "Strict",
                "entry": "n",
                "nodes": {"n": {"type": "resource"}},
                "edges": [{"from_node": "n", "to_node": None}],
            }
        )


@pytest.mark.asyncio
async def test_create_node_requires_node_constructor() -> None:
    with pytest.raises(TypeError, match="node_constructor"):
        _ = await create_node("n", {"type": "resource"})


def test_side_effect_node_constructor_requires_execution() -> None:
    with pytest.raises(TypeError, match="execution"):
        _ = CodeNode("code", config={"type": "code", "code": "def execute(args, state): pass"})


@pytest.mark.asyncio
async def test_flow_run_requires_existing_workflow_instance() -> None:
    runtime = _NoWorkflowRuntime()
    execution = execution_context_for(runtime)
    redis_client = RedisClient.__new__(RedisClient)
    flow = Flow(
        flow_id="strict_flow",
        name="Strict",
        entry="n",
        nodes={"n": _PureNode("n", {"type": "resource"}, execution=execution, redis_client=redis_client)},
        edges=[],
        interface=default_chat_document(),
        execution=execution,
        emitter_factory=EmitterFactory.__new__(EmitterFactory),
    )

    with pytest.raises(RuntimeError, match="requires durable workflow instance"):
        _ = await flow.run(_state())


@pytest.mark.asyncio
async def test_side_effect_node_run_requires_existing_workflow_instance() -> None:
    runtime = _NoWorkflowRuntime()
    node = CodeNode(
        "code",
        config={"type": "code", "code": "def execute(args, state): return {}"},
        execution=execution_context_for(runtime),
        redis_client=RedisClient.__new__(RedisClient),
    )

    with pytest.raises(RuntimeError, match="requires durable workflow instance"):
        _ = await node.run(_state())
