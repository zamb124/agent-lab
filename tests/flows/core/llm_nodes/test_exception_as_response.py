"""Тесты режима exception_as_response для LlmNodeRunner и BaseNode."""

from typing import Any, Dict

import pytest

from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMOverride
from apps.flows.src.runtime.nodes import BaseNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from core.state import ExecutionState


def _minimal_state() -> ExecutionState:
    return ExecutionState(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow1:c1",
    )


class _FailingTool:
    name = "fail_tool"

    async def run(self, args: Dict[str, Any], state: ExecutionState) -> str:
        raise TypeError("tool failed")


class _FailingNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: Dict[str, Any]) -> Any:
        raise ValueError("node failed")


@pytest.mark.asyncio
async def test_llm_runner_absorbs_tool_error_when_enabled() -> None:
    cfg = NodeConfig(
        node_id="agent1",
        type=NodeType.LLM_NODE,
        name="A",
        description="",
        llm=NodeLLMOverride(provider="mock"),
        exception_as_response=True,
        exception_allow_types=[],
    )
    runner = LlmNodeRunner(
        node_config=cfg,
        tools=[_FailingTool()],
        llm=None,
        prompt="p",
    )
    state = _minimal_state()
    out = await runner._execute_single_tool(
        {"name": "fail_tool", "id": "tc1", "arguments": {}},
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
async def test_llm_runner_raises_when_policy_off() -> None:
    from core.errors import ToolExecutionError

    cfg = NodeConfig(
        node_id="agent1",
        type=NodeType.LLM_NODE,
        name="A",
        description="",
        llm=NodeLLMOverride(provider="mock"),
        exception_as_response=False,
    )
    runner = LlmNodeRunner(
        node_config=cfg,
        tools=[_FailingTool()],
        llm=None,
        prompt="p",
    )
    state = _minimal_state()
    with pytest.raises(ToolExecutionError):
        await runner._execute_single_tool(
            {"name": "fail_tool", "id": "tc1", "arguments": {}},
            state,
        )


@pytest.mark.asyncio
async def test_base_node_absorbs_run_impl_error_when_enabled() -> None:
    node = _FailingNode(
        "n1",
        {"exception_as_response": True, "exception_allow_types": []},
    )
    state = _minimal_state()
    await node._run_internal(state)
    assert len(state.execution_exceptions) == 1
    assert state.execution_exceptions[0].source == "node_run"
    assert state.execution_exceptions[0].exception_type == "ValueError"
    assert state.error is True
    assert state.error_type == "ValueError"


@pytest.mark.asyncio
async def test_base_node_raises_when_whitelist_mismatch() -> None:
    node = _FailingNode(
        "n1",
        {"exception_as_response": True, "exception_allow_types": ["RuntimeError"]},
    )
    state = _minimal_state()
    with pytest.raises(ValueError, match="node failed"):
        await node._run_internal(state)
