"""Тесты режима exception_as_response для LlmNodeRunner и BaseNode."""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.nodes import BaseNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.tools.base import BaseTool
from core.clients.llm import LLMToolCall
from core.state import ExecutionState
from core.types import JsonObject
from tests.flows.durable_runtime_harness import ensure_workflow_started


def _minimal_state(unique_id: str) -> ExecutionState:
    flow_id = f"flow_{unique_id}"
    context_id = f"ctx_{unique_id}"
    return ExecutionState(
        task_id=f"task_{unique_id}",
        context_id=context_id,
        user_id="u1",
        session_id=f"{flow_id}:{context_id}",
    )


class _FailingTool(BaseTool):
    name = "fail_tool"
    description = "Raises TypeError"

    async def _run_impl(self, args: JsonObject, state: ExecutionState) -> str:
        _ = args, state
        raise TypeError("tool failed")


class _FailingNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: JsonObject) -> JsonObject:
        _ = state, inputs
        raise ValueError("node failed")


@pytest.mark.asyncio
async def test_llm_runner_absorbs_tool_error_when_enabled(app, unique_id: str) -> None:
    _ = app
    cfg = NodeConfig(
        node_id="agent1",
        type=NodeType.LLM_NODE,
        name="A",
        description="",
        llm=NodeLLMConfig(provider="mock"),
        exception_as_response=True,
        exception_allow_types=[],
    )
    runner = LlmNodeRunner(
        node_config=cfg,
        tools=[_FailingTool()],
        llm=None,
        prompt="p",
        container=get_container(),
    )
    state = _minimal_state(unique_id)
    await ensure_workflow_started(
        container=get_container(),
        state=state,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
    )
    out = await runner._execute_single_tool(
        LLMToolCall(name="fail_tool", id="tc1", arguments={}),
        state,
    )
    assert len(out) == 1
    assert out[0]["tool_call_id"] == "tc1"
    assert "TypeError" in out[0]["content"]
    assert "tool failed" in out[0]["content"]
    assert len(state.execution_exceptions) == 1
    assert state.execution_exceptions[0].source == "tool"
    assert state.execution_exceptions[0].exception_type == "TypeError"


@pytest.mark.asyncio
async def test_llm_runner_raises_when_policy_off(app, unique_id: str) -> None:
    _ = app
    from core.errors import ToolExecutionError

    cfg = NodeConfig(
        node_id="agent1",
        type=NodeType.LLM_NODE,
        name="A",
        description="",
        llm=NodeLLMConfig(provider="mock"),
        exception_as_response=False,
    )
    runner = LlmNodeRunner(
        node_config=cfg,
        tools=[_FailingTool()],
        llm=None,
        prompt="p",
        container=get_container(),
    )
    state = _minimal_state(unique_id)
    await ensure_workflow_started(
        container=get_container(),
        state=state,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
    )
    with pytest.raises(ToolExecutionError):
        await runner._execute_single_tool(
            LLMToolCall(name="fail_tool", id="tc1", arguments={}),
            state,
        )


@pytest.mark.asyncio
async def test_base_node_absorbs_run_impl_error_when_enabled(app, unique_id: str) -> None:
    _ = app
    node = _FailingNode(
        "n1",
        {"type": "test_failing", "exception_as_response": True, "exception_allow_types": []},
        container=get_container(),
    )
    state = _minimal_state(unique_id)
    await node.execute(state)
    assert len(state.execution_exceptions) == 1
    assert state.execution_exceptions[0].source == "node_run"
    assert state.execution_exceptions[0].exception_type == "ValueError"
    assert state.error is True
    assert state.error_type == "ValueError"


@pytest.mark.asyncio
async def test_base_node_raises_when_whitelist_mismatch(app, unique_id: str) -> None:
    _ = app
    node = _FailingNode(
        "n1",
        {"type": "test_failing", "exception_as_response": True, "exception_allow_types": ["RuntimeError"]},
        container=get_container(),
    )
    state = _minimal_state(unique_id)
    with pytest.raises(ValueError, match="node failed"):
        await node.execute(state)
