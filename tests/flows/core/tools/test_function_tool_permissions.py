"""FunctionTool permission checks via OpenFGA company membership."""

from __future__ import annotations

import pytest

from apps.flows.src.state import ExecutionState
from apps.flows.tools.misc.math_tools import calculator
from core.context import set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.fixtures.auth import set_test_company_member_roles


@pytest.mark.asyncio
async def test_function_tool_permission_denied_without_company_membership(
    di, unique_id
) -> None:
    _ = di
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
    di,
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
    await User.set(user)
    await Company.set(company)
    await set_test_company_member_roles(
        di.authz_service,
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
