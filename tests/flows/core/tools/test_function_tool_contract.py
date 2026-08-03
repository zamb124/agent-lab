"""FunctionTool contract metadata and permission inheritance."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from apps.flows.config import get_settings
from apps.flows.src.tools.decorator import FunctionTool, tool
from core.state import ExecutionState


class _EchoArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1, description="Value to echo.")


@tool(
    name="contract_echo_tool",
    description="Echoes value for contract tests.",
    tags=["misc"],
    permission=["managers"],
    parameters_model=_EchoArgs,
    effects=["read"],
    confirmation_floor="preview",
    idempotency="supported",
    argument_sources={"value": "model"},
    output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
)
async def contract_echo_tool(value: str) -> dict[str, str]:
    return {"value": value}


@pytest.mark.asyncio
async def test_function_tool_inherits_contract_metadata() -> None:
    assert isinstance(contract_echo_tool, FunctionTool)
    assert contract_echo_tool.effects == ["read"]
    assert contract_echo_tool.confirmation_floor == "preview"
    assert contract_echo_tool.idempotency == "supported"
    assert contract_echo_tool.argument_sources == {"value": "model"}
    assert contract_echo_tool.output_schema == {
        "type": "object",
        "properties": {"value": {"type": "string"}},
    }


@pytest.mark.asyncio
async def test_function_tool_inherits_permission_check() -> None:
    config = get_settings()
    original_permissions = config.auth.permissions_enabled
    config.auth.permissions_enabled = True
    try:
        state = ExecutionState(
            task_id="task-1",
            context_id="ctx-1",
            user_id="user-1",
            session_id="flow:ctx-1",
            user_groups=["users"],
        )
        denied = await contract_echo_tool.run({"value": "hello"}, state)
        assert isinstance(denied, str)
        assert "нет прав" in denied

        state_allowed = state.model_copy(update={"user_groups": ["managers"]})
        allowed = await contract_echo_tool.run({"value": "hello"}, state_allowed)
        assert allowed == {"value": "hello"}
    finally:
        config.auth.permissions_enabled = original_permissions
