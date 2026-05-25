from __future__ import annotations

from typing import cast

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, CodeNode, NodeInputs, NodeRunResult, create_node
from core.state import ExecutionState


class _NoWorkflowRuntime:
    async def get_active_execution_position(self, session_id: str) -> None:
        _ = session_id
        return None


class _StrictRuntimeContainer:
    workflow_runtime = _NoWorkflowRuntime()
    redis_client = object()

    def get_code_runner(self, language: str) -> object:
        raise AssertionError(f"runner must not be requested before durable context: {language}")


class _PureNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = state
        _ = inputs
        return None


def _container() -> FlowRuntimeContainer:
    return cast(FlowRuntimeContainer, _StrictRuntimeContainer())


def _state() -> ExecutionState:
    return ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="strict_flow:ctx",
    )


@pytest.mark.asyncio
async def test_flow_from_config_requires_runtime_container() -> None:
    with pytest.raises(TypeError, match="container"):
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
async def test_create_node_requires_runtime_container() -> None:
    with pytest.raises(TypeError, match="container"):
        _ = await create_node("n", {"type": "resource"})


def test_side_effect_node_constructor_requires_runtime_container() -> None:
    with pytest.raises(TypeError, match="container"):
        _ = CodeNode("code", config={"type": "code", "code": "def execute(args, state): pass"})


@pytest.mark.asyncio
async def test_flow_run_requires_existing_workflow_instance() -> None:
    container = _container()
    flow = Flow(
        flow_id="strict_flow",
        name="Strict",
        entry="n",
        nodes={"n": _PureNode("n", {"type": "resource"}, container=container)},
        edges=[],
        container=container,
    )

    with pytest.raises(RuntimeError, match="requires durable workflow instance"):
        _ = await flow.run(_state())


@pytest.mark.asyncio
async def test_side_effect_node_run_requires_existing_workflow_instance() -> None:
    node = CodeNode(
        "code",
        config={"type": "code", "code": "def execute(args, state): return {}"},
        container=_container(),
    )

    with pytest.raises(RuntimeError, match="requires durable workflow instance"):
        _ = await node.run(_state())
