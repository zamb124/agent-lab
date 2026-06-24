"""Agent tools work_item_create/complete/list — edge cases."""

from __future__ import annotations

import pytest

from apps.flows.tools.work_item_tools import work_item_complete, work_item_create, work_item_list
from core.state import ExecutionState
from core.worktracker.models import AssigneeKind, WorkItemState

pytestmark = pytest.mark.asyncio


async def test_work_item_create_agent_assignee(app, container, unique_id: str) -> None:
    state = ExecutionState(
        task_id=f"t-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="test_user",
        session_id=f"flow_{unique_id}:ctx-{unique_id}",
        branch_id="default",
    )
    result = await work_item_create(
        state,
        title=f"Agent task {unique_id}",
        assignee_type="agent",
        assignee_flow_id=f"flow_{unique_id}",
    )
    assert result["work_item_id"]
    item = await container.work_item_service.get("system", result["work_item_id"])
    assert item.assignment.assignee_kind == AssigneeKind.AGENT


async def test_work_item_list_state_filter(app, container, unique_id: str) -> None:
    svc = container.work_item_service
    from core.worktracker.models import SystemActor

    open_item = await svc.create(
        company_id="system",
        title=f"open-{unique_id}",
        created_by=SystemActor(),
    )
    done_item = await svc.create(
        company_id="system",
        title=f"done-{unique_id}",
        created_by=SystemActor(),
    )
    await svc.complete(company_id="system", work_item_id=done_item.work_item_id)

    state = ExecutionState(
        task_id=f"t2-{unique_id}",
        context_id=f"ctx2-{unique_id}",
        user_id="test_user",
        session_id=f"flow2_{unique_id}:ctx2",
        branch_id="default",
    )
    listed = await work_item_list(state, state_filter="open")
    ids = {entry["work_item_id"] for entry in listed["items"]}
    assert open_item.work_item_id in ids
    assert done_item.work_item_id not in ids


async def test_work_item_create_missing_assignee_flow_id_raises(app, unique_id: str) -> None:
    state = ExecutionState(
        task_id=f"t3-{unique_id}",
        context_id=f"ctx3-{unique_id}",
        user_id="test_user",
        session_id=f"flow3_{unique_id}:ctx3",
        branch_id="default",
    )
    with pytest.raises(ValueError):
        await work_item_create(
            state,
            title="bad",
            assignee_type="agent",
        )


async def test_work_item_complete_with_resolution(app, container, unique_id: str) -> None:
    from core.worktracker.models import SystemActor

    item = await container.work_item_service.create(
        company_id="system",
        title=f"complete-tool-{unique_id}",
        created_by=SystemActor(),
    )
    state = ExecutionState(
        task_id=f"t4-{unique_id}",
        context_id=f"ctx4-{unique_id}",
        user_id="test_user",
        session_id=f"flow4_{unique_id}:ctx4",
        branch_id="default",
    )
    result = await work_item_complete(
        state,
        work_item_id=item.work_item_id,
        resolution_text="done via tool",
    )
    assert result["state"] == WorkItemState.DONE.value
