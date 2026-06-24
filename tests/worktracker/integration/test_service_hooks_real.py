"""Real ServiceClientHookDispatcher → flows internal endpoints (ASGI patch)."""

from __future__ import annotations

import pytest

from core.worktracker.models import (
    AgentAssignment,
    SystemActor,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
)

pytestmark = pytest.mark.asyncio


async def test_assigned_hook_hits_flows_internal(app, worktracker_service, unique_id: str) -> None:
    flow_id = f"flow_hook_{unique_id}"
    item = await worktracker_service.create(
        company_id="system",
        title=f"hook-{unique_id}",
        created_by=SystemActor(),
        kind=WorkItemKind.AGENT_JOB,
        assignment=AgentAssignment(flow_id=flow_id),
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
    assert isinstance(fetched.assignment, AgentAssignment)


async def test_reassign_to_agent_dispatches_assigned_hook(
    app,
    worktracker_service,
    unique_id: str,
) -> None:
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
    flow_id = f"flow_re_{unique_id}"
    reassigned = await worktracker_service.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=AgentAssignment(flow_id=flow_id),
    )
    assert isinstance(reassigned.assignment, AgentAssignment)
    assert reassigned.assignment.flow_id == flow_id
