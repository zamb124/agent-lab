"""FunctionTool permission checks via OpenFGA company membership."""

from __future__ import annotations

import pytest

from apps.flows.tools.misc.math_tools import calculator
from core.context import set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.state import ExecutionState
from tests.fixtures.auth import set_test_company_member_roles


@pytest.mark.asyncio
async def test_function_tool_permission_denied_without_company_membership(
    container, unique_id
) -> None:
    _ = container
    state = ExecutionState(
        task_id="perm-task",
        context_id="perm-context",
        user_id=f"perm-user-{unique_id}",
        session_id="perm-flow:perm-context",
        user_groups=[],
    )
    result = await calculator.run({"expression": "2 + 2"}, state)
    assert isinstance(result, str)
    assert "нет прав" in result.lower()
    assert "calculator" in result


@pytest.mark.asyncio
async def test_function_tool_permission_granted_for_company_member(
    container,
    unique_id,
) -> None:
    user_id = f"member-{unique_id}"
    company_id = f"co-{unique_id}"
    user = User(
        user_id=user_id,
        name="Member",
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name="Co",
        members={user_id: ["member"]},
    )
    await container.user_repository.set(user)
    await container.company_repository.set(company)
    await set_test_company_member_roles(
        container.company_repository,
        container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["member"],
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="api",
        )
    )
    state = ExecutionState(
        task_id="perm-task",
        context_id="perm-context",
        user_id=user_id,
        session_id="perm-flow:perm-context",
        user_groups=[],
    )
    result = await calculator.run({"expression": "2 + 2"}, state)
    assert isinstance(result, str)
    assert "4" in result
