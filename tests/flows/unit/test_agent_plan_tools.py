"""Unit tests for agent_plan_write / agent_plan_get."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from pydantic import ValidationError

from apps.flows.src.agent_plan.models import AgentPlanStepStatus
from apps.flows.src.state import ExecutionState
from apps.flows.tools.flows.agent_plan_tools import agent_plan_get, agent_plan_write
from tests.flows._tool_authz_context import bind_flow_tool_authz_context


@pytest.fixture
def execution_state() -> ExecutionState:
    return ExecutionState.create(
        task_id="task-agent-plan",
        context_id="ctx-agent-plan",
        user_id="user-agent-plan",
        session_id="flow-agent-plan:ctx-agent-plan",
    )


@pytest_asyncio.fixture(autouse=True)
async def _agent_plan_tools_authz_context(
    execution_state: ExecutionState,
    di,
) -> AsyncIterator[None]:
    async for _ in bind_flow_tool_authz_context(extra_user_ids=[execution_state.user_id], di=di):
        yield


@pytest.mark.asyncio
async def test_agent_plan_write_overwrites_state(execution_state: ExecutionState) -> None:
    first = await agent_plan_write.run(
        {
            "steps": [
                {"id": "1", "title": "Step one", "status": "in_progress"},
                {"id": "2", "title": "Step two", "status": "pending"},
            ]
        },
        execution_state,
    )
    assert isinstance(first, dict)
    assert first["agent_plan_id"]
    assert execution_state.agent_plan is not None
    assert execution_state.agent_plan.steps[0].title == "Step one"
    assert first["blocks"][0]["type"] == "agent_plan"

    plan_id = first["agent_plan_id"]
    second = await agent_plan_write.run(
        {
            "steps": [
                {"id": "1", "title": "Step one", "status": "completed"},
                {"id": "2", "title": "Step two", "status": "in_progress"},
            ]
        },
        execution_state,
    )
    assert isinstance(second, dict)
    assert second["agent_plan_id"] == plan_id
    assert execution_state.agent_plan is not None
    assert execution_state.agent_plan.steps[0].status == AgentPlanStepStatus.COMPLETED
    assert execution_state.agent_plan.steps[1].status == AgentPlanStepStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_agent_plan_get_reads_state(execution_state: ExecutionState) -> None:
    await agent_plan_write.run(
        {"steps": [{"id": "1", "title": "Only", "status": "in_progress"}]},
        execution_state,
    )
    payload = await agent_plan_get.run({}, execution_state)
    assert isinstance(payload, dict)
    assert payload["plan"]["steps"][0]["title"] == "Only"
    assert payload["blocks"][0]["plan"]["steps"][0]["step_id"] == "1"


@pytest.mark.asyncio
async def test_agent_plan_get_without_plan_raises(execution_state: ExecutionState) -> None:
    with pytest.raises(ValueError, match="missing"):
        await agent_plan_get.run({}, execution_state)


@pytest.mark.asyncio
async def test_agent_plan_write_empty_steps_raises(execution_state: ExecutionState) -> None:
    with pytest.raises(ValidationError):
        await agent_plan_write.run({"steps": []}, execution_state)
