"""Agent tools work_item_create/complete/list — edge cases."""

from __future__ import annotations

import pytest

from apps.flows.tools.work_item_tools import work_item_complete, work_item_create, work_item_list
from core.identity.flow_employee import flow_employee_user_id
from tests.fixtures.flow_employee_test_helpers import (
    cleanup_flow_employee_for_tests,
    provision_flow_employee_for_tests,
)
from core.state import ExecutionState
from core.worktracker.models import (
    ActorKind,
    AssigneeKind,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItemState,
)

pytestmark = pytest.mark.asyncio


async def test_work_item_create_agent_assignee(app, container, unique_id: str) -> None:
    flow_id = f"flow_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        state = ExecutionState(
            task_id=f"t-{unique_id}",
            context_id=f"ctx-{unique_id}",
            user_id="test_user",
            session_id=f"flow_{unique_id}:ctx-{unique_id}",
            branch_id="default",
        )
        result = await work_item_create.run(
            {
                "title": f"Agent task {unique_id}",
                "assignee_type": "agent",
                "assignee_flow_id": flow_id,
            },
            state,
        )
        assert result["work_item_id"]
        item = await container.work_item_service.get("system", result["work_item_id"])
        assert item.assignment.assignee_kind == AssigneeKind.USERS
        assert isinstance(item.assignment, UsersAssignment)
        assert item.assignment.user_ids == [flow_employee_user_id(flow_id)]
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)


async def test_work_item_list_state_filter(app, container, unique_id: str) -> None:
    svc = container.work_item_service

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
    listed = await work_item_list.run({"state_filter": "open"}, state)
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
        await work_item_create.run(
            {"title": "bad", "assignee_type": "agent"},
            state,
        )


async def test_work_item_complete_with_resolution(app, container, unique_id: str) -> None:
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
    result = await work_item_complete.run(
        {
            "work_item_id": item.work_item_id,
            "resolution_text": "done via tool",
        },
        state,
    )
    assert result["state"] == WorkItemState.DONE.value


async def test_work_item_create_self_assigns_employee_of_session_flow(
    app, container, unique_id: str
) -> None:
    flow_id = f"self_flow_{unique_id}"
    await provision_flow_employee_for_tests(
        flow_id=flow_id,
        curator_user_id=f"cur_{unique_id}",
    )
    try:
        state = ExecutionState(
            task_id=f"ts-{unique_id}",
            context_id=f"ctxs-{unique_id}",
            user_id="test_user",
            session_id=f"{flow_id}:ctxs-{unique_id}",
            branch_id="default",
        )
        result = await work_item_create.run(
            {"title": f"self task {unique_id}", "assignee_type": "self"},
            state,
        )
        item = await container.work_item_service.get("system", result["work_item_id"])
        assert isinstance(item.assignment, UsersAssignment)
        assert item.assignment.user_ids == [flow_employee_user_id(flow_id)]
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)


async def test_work_item_create_records_actor_created_by(app, container, unique_id: str) -> None:
    state = ExecutionState(
        task_id=f"tc-{unique_id}",
        context_id=f"ctxc-{unique_id}",
        user_id="test_user",
        session_id=f"flowc_{unique_id}:ctxc",
        branch_id="default",
    )
    result = await work_item_create.run({"title": f"actor {unique_id}"}, state)
    item = await container.work_item_service.get("system", result["work_item_id"])
    assert item.created_by.actor_kind == ActorKind.USER
    assert isinstance(item.created_by, UserActor)
    assert item.created_by.user_id == "test_user"


async def test_work_item_create_user_and_unassigned(app, container, unique_id: str) -> None:
    state = ExecutionState(
        task_id=f"tu-{unique_id}",
        context_id=f"ctxu-{unique_id}",
        user_id="test_user",
        session_id=f"flowu_{unique_id}:ctxu",
        branch_id="default",
    )
    human = await work_item_create.run(
        {"title": f"human {unique_id}", "assignee_type": "user", "assignee_user_id": "human_x"},
        state,
    )
    human_item = await container.work_item_service.get("system", human["work_item_id"])
    assert isinstance(human_item.assignment, UsersAssignment)
    assert human_item.assignment.user_ids == ["human_x"]

    none = await work_item_create.run(
        {"title": f"none {unique_id}", "assignee_type": "unassigned"},
        state,
    )
    none_item = await container.work_item_service.get("system", none["work_item_id"])
    assert isinstance(none_item.assignment, UnassignedAssignment)
    assert none_item.assignment.assignee_kind == AssigneeKind.UNASSIGNED


async def test_work_item_create_user_missing_id_raises(app, unique_id: str) -> None:
    state = ExecutionState(
        task_id=f"te-{unique_id}",
        context_id=f"ctxe-{unique_id}",
        user_id="test_user",
        session_id=f"flowe_{unique_id}:ctxe",
        branch_id="default",
    )
    with pytest.raises(ValueError):
        await work_item_create.run({"title": "bad", "assignee_type": "user"}, state)
