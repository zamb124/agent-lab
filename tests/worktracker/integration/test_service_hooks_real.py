"""ServiceClientHookDispatcher → flows internal endpoints через HTTP flows_service."""

from __future__ import annotations

import pytest

from core.identity.flow_employee import flow_employee_user_id
from core.worktracker.models import (
    SystemActor,
    UsersAssignment,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
)
from tests.fixtures.flow_employee_test_helpers import (
    cleanup_flow_employee_for_tests,
    provision_flow_employee_for_tests,
)

pytestmark = pytest.mark.asyncio


async def test_assigned_hook_hits_flows_internal(
    app,
    flows_service,
    worktracker_service,
    unique_id: str,
) -> None:
    _ = app
    flow_id = f"flow_hook_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        item = await worktracker_service.create(
            company_id="system",
            title=f"hook-{unique_id}",
            created_by=SystemActor(),
            kind=WorkItemKind.AGENT_JOB,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(flow_id)]),
            hooks=[
                WorkItemHook(
                    event=WorkItemHookEvent.ASSIGNED,
                    service="flows",
                    path="/flows/api/v1/internal/work-items/assigned",
                )
            ],
        )
        fetched = await worktracker_service.get("system", item.work_item_id)
        assert fetched.work_item_id == item.work_item_id
        assert isinstance(fetched.assignment, UsersAssignment)
        assert fetched.assignment.user_ids == [flow_employee_user_id(flow_id)]
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)


async def test_reassign_to_agent_dispatches_assigned_hook(
    app,
    flows_service,
    worktracker_service,
    unique_id: str,
) -> None:
    _ = app
    flow_id = f"flow_re_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        item = await worktracker_service.create(
            company_id="system",
            title=f"reassign-hook-{unique_id}",
            created_by=SystemActor(),
            kind=WorkItemKind.AGENT_JOB,
            hooks=[
                WorkItemHook(
                    event=WorkItemHookEvent.ASSIGNED,
                    service="flows",
                    path="/flows/api/v1/internal/work-items/assigned",
                )
            ],
        )
        reassigned = await worktracker_service.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(flow_id)]),
        )
        assert isinstance(reassigned.assignment, UsersAssignment)
        assert reassigned.assignment.user_ids == [flow_employee_user_id(flow_id)]
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)
