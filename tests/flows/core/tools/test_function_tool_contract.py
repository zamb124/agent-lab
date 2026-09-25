"""FunctionTool contract metadata and OpenFGA permission inheritance."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import FunctionTool, tool
from core.authz.group_sync import sync_user_groups
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
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
async def test_function_tool_inherits_permission_check(di, unique_id) -> None:
    denied_user = f"echo-denied-{unique_id}"
    allowed_user = f"echo-allowed-{unique_id}"
    company_id = f"echo-co-{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=denied_user,
        groups=["users"],
        company_ids=[company_id],
        previous_groups=[],
    )
    await sync_user_groups(
        di.authz_service,
        user_id=allowed_user,
        groups=["managers"],
        company_ids=[company_id],
        previous_groups=[],
    )
    company = Company(company_id=company_id, name="Echo Co")
    set_context(
        Context(
            user=User(user_id=allowed_user, name="Allowed", groups=["managers"]),
            active_company=company,
            channel="api",
        )
    )
    try:
        denied = await contract_echo_tool.run(
            {"value": "hello"},
            ExecutionState(
                task_id="task-1",
                context_id="ctx-1",
                user_id=denied_user,
                session_id="flow:ctx-1",
            ),
        )
        assert isinstance(denied, str)
        assert "нет прав" in denied

        allowed = await contract_echo_tool.run(
            {"value": "hello"},
            ExecutionState(
                task_id="task-2",
                context_id="ctx-2",
                user_id=allowed_user,
                session_id="flow:ctx-2",
            ),
        )
        assert allowed == {"value": "hello"}
    finally:
        clear_context()
