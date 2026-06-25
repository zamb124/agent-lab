"""ServiceClientHookDispatcher → flows internal endpoints через HTTP flows_service."""

from __future__ import annotations

import pytest

from apps.flows.src.models import FlowConfig
from core.worktracker.models import (
    AgentAssignment,
    SystemActor,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
)

pytestmark = pytest.mark.asyncio


async def _seed_minimal_flow(container, flow_id: str) -> None:
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"Hook flow {flow_id}",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": (
                    "async def run(args, state):\n"
                    "    state['response'] = 'ok'\n"
                    "    return state"
                ),
            },
        },
        edges=[{"from_node": "main", "to_node": None}],
    )
    await container.flow_repository.set(flow_config)


async def test_assigned_hook_hits_flows_internal(
    app,
    flows_service,
    worktracker_service,
    unique_id: str,
) -> None:
    _ = app
    from apps.flows.src.container import get_container

    flow_id = f"flow_hook_{unique_id}"
    await _seed_minimal_flow(get_container(), flow_id)

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
    flows_service,
    worktracker_service,
    unique_id: str,
) -> None:
    _ = app
    from apps.flows.src.container import get_container

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
    await _seed_minimal_flow(get_container(), flow_id)
    reassigned = await worktracker_service.reassign(
        company_id="system",
        work_item_id=item.work_item_id,
        assignment=AgentAssignment(flow_id=flow_id),
    )
    assert isinstance(reassigned.assignment, AgentAssignment)
    assert reassigned.assignment.flow_id == flow_id
