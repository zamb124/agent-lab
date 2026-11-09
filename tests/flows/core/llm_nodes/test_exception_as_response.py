"""Тесты режима exception_as_response для LlmNodeRunner и BaseNode."""

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import BaseNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.flows.agent_skill_tools import read_agent_skill_reference
from core.clients.llm import LLMToolCall
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


class _StrictArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    required_field: str = Field(..., min_length=1)


@tool(
    name="strict_args_tool",
    description="Requires required_field",
    tags=["test"],
    parameters_model=_StrictArgs,
    listed_in_platform_tool_docs=False,
)
async def _strict_args_tool(required_field: str, *, state: ExecutionState) -> str:
    _ = state
    return required_field


class _FailingNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: JsonObject) -> JsonObject:
        _ = state, inputs
        raise ValueError("node failed")


@pytest.mark.asyncio
async def test_llm_runner_absorbs_tool_error_when_enabled(app, unique_id: str, di) -> None:
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
        workflow_runtime=di.node_constructor.workflow_runtime, memory_store=di.node_constructor.llm_context_memory_store, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, redis_client=di.node_constructor.redis_client, tool_registry=di.tool_registry, billing_service=di.node_constructor.billing_service,
    )
    state = _minimal_state(unique_id)
    await ensure_workflow_started(
        di=di,
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
async def test_llm_runner_raises_when_policy_off(app, unique_id: str, di) -> None:
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
        workflow_runtime=di.node_constructor.workflow_runtime, memory_store=di.node_constructor.llm_context_memory_store, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, redis_client=di.node_constructor.redis_client, tool_registry=di.tool_registry, billing_service=di.node_constructor.billing_service,
    )
    state = _minimal_state(unique_id)
    await ensure_workflow_started(
        di=di,
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
async def test_llm_runner_absorbs_arg_validation_error_when_policy_off(
    app, unique_id: str,
    di,
) -> None:
    """Невалидные args tool — всегда tool result, даже при exception_as_response=false."""
    _ = app
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
        tools=[_strict_args_tool],
        llm=None,
        prompt="p",
        workflow_runtime=di.node_constructor.workflow_runtime, memory_store=di.node_constructor.llm_context_memory_store, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, redis_client=di.node_constructor.redis_client, tool_registry=di.tool_registry, billing_service=di.node_constructor.billing_service,
    )
    state = _minimal_state(unique_id)
    await ensure_workflow_started(
        di=di,
        state=state,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
    )
    out = await runner._execute_single_tool(
        LLMToolCall(name="strict_args_tool", id="tc_val", arguments={}),
        state,
    )
    assert len(out) == 1
    assert out[0]["tool_call_id"] == "tc_val"
    assert "ValidationError" in out[0]["content"]
    assert "required_field" in out[0]["content"]
    assert len(state.execution_exceptions) == 1
    assert state.execution_exceptions[0].source == "tool"
    assert state.execution_exceptions[0].exception_type == "ValidationError"


def test_read_agent_skill_reference_description_excludes_documents() -> None:
    description = read_agent_skill_reference.description
    assert "documents_read" in description
    assert "Documents library" in description or "SPA UI" in description


@pytest.mark.asyncio
async def test_base_node_absorbs_run_impl_error_when_enabled(app, unique_id: str, di) -> None:
    _ = app
    node = _FailingNode(
        "n1",
        {"type": "test_failing", "exception_as_response": True, "exception_allow_types": []},
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client,
    )
    state = _minimal_state(unique_id)
    await node.execute(state)
    assert len(state.execution_exceptions) == 1
    assert state.execution_exceptions[0].source == "node_run"
    assert state.execution_exceptions[0].exception_type == "ValueError"
    assert state.error is True
    assert state.error_type == "ValueError"


@pytest.mark.asyncio
async def test_base_node_raises_when_whitelist_mismatch(app, unique_id: str, di) -> None:
    _ = app
    node = _FailingNode(
        "n1",
        {"type": "test_failing", "exception_as_response": True, "exception_allow_types": ["RuntimeError"]},
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client,
    )
    state = _minimal_state(unique_id)
    with pytest.raises(ValueError, match="node failed"):
        await node.execute(state)
