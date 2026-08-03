"""Permission enforcement для FunctionTool через BaseTool.run."""

import pytest

from apps.flows.tools.math_tools import calculator
from core.state import ExecutionState


@pytest.mark.asyncio
async def test_function_tool_permission_denied_without_groups(flows_permissions_enabled) -> None:
    _ = flows_permissions_enabled
    state = ExecutionState(
        task_id="perm-task",
        context_id="perm-context",
        user_id="perm-user",
        session_id="perm-flow:perm-context",
        user_groups=[],
    )
    result = await calculator.run({"expression": "2 + 2"}, state)
    assert isinstance(result, str)
    assert "нет прав" in result.lower()
    assert "calculator" in result


@pytest.mark.asyncio
async def test_function_tool_permission_granted_with_standard_group(
    flows_permissions_enabled,
) -> None:
    _ = flows_permissions_enabled
    state = ExecutionState(
        task_id="perm-task",
        context_id="perm-context",
        user_id="perm-user",
        session_id="perm-flow:perm-context",
        user_groups=["guest"],
    )
    result = await calculator.run({"expression": "2 + 2"}, state)
    assert isinstance(result, str)
    assert "4" in result
