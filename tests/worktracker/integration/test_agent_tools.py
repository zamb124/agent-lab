"""Agent tools work_item_* — create/list/list_mine/complete and related edge cases."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from apps.flows.src.tools.builtin_dependencies import BuiltinToolClient
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.tools.worktracker.work_item_tools import (
    work_item_complete,
    work_item_create,
    work_item_get,
    work_item_list,
    work_item_list_mine,
)
from core.identity.flow_employee import flow_employee_user_id
from core.state import ExecutionState
from core.worktracker.models import (
    ActorKind,
    AssigneeKind,
    SystemActor,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemState,
)
from tests.fixtures.flow_employee_test_helpers import (
    cleanup_flow_employee_for_tests,
    provision_flow_employee_for_tests,
)

pytestmark = pytest.mark.asyncio


def _bound(
    tool: FunctionTool,
    clients: Sequence[BuiltinToolClient],
) -> FunctionTool:
    return tool.with_dependencies(clients)


async def test_work_item_create_agent_assignee(builtin_tool_clients, app, unique_id: str, di) -> None:
    flow_id = f"flow_{unique_id}"
    await provision_flow_employee_for_tests(
        di=di,
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
        result = await _bound(work_item_create, builtin_tool_clients).run(
            {
                "title": f"Agent task {unique_id}",
                "assignee_type": "agent",
                "assignee_flow_id": flow_id,
            },
            state,
        )
        assert result["work_item_id"]
        assert result["board_id"]
        item = await WorkItem.require_in_company("system", result["work_item_id"])
        assert item.assignment.assignee_kind == AssigneeKind.USERS
        assert isinstance(item.assignment, UsersAssignment)
        assert item.assignment.user_ids == [flow_employee_user_id(flow_id)]
        assert item.board_id is not None
    finally:
        await cleanup_flow_employee_for_tests(di=di,flow_id=flow_id)


async def test_work_item_list_state_filter(builtin_tool_clients, app, di, unique_id: str) -> None:
    svc = di.work_item_service

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
    listed = await _bound(work_item_list, builtin_tool_clients).run({"state_filter": "open"}, state)
    ids = {entry["work_item_id"] for entry in listed["items"]}
    assert open_item.work_item_id in ids
    assert done_item.work_item_id not in ids


async def test_work_item_list_mine_scopes_to_current_user(
    builtin_tool_clients,
    app, di, unique_id: str
) -> None:
    other_id = f"other_{unique_id}"
    await di.work_item_service.create(
        company_id="system",
        title=f"other-{unique_id}",
        created_by=SystemActor(),
        assignment=UsersAssignment(user_ids=[other_id]),
    )
    mine = await di.work_item_service.create(
        company_id="system",
        title=f"mine-{unique_id}",
        created_by=SystemActor(),
        assignment=UsersAssignment(user_ids=["test_user"]),
    )
    state = ExecutionState(
        task_id=f"tm-{unique_id}",
        context_id=f"ctxm-{unique_id}",
        user_id="test_user",
        session_id=f"flowm_{unique_id}:ctxm",
        branch_id="default",
    )
    listed = await _bound(work_item_list_mine, builtin_tool_clients).run({}, state)
    ids = {entry["work_item_id"] for entry in listed["items"]}
    assert mine.work_item_id in ids
    assert listed["assignee_user_id"] == "test_user"


async def test_work_item_get_returns_detail(builtin_tool_clients, app, di, unique_id: str) -> None:
    item = await di.work_item_service.create(
        company_id="system",
        title=f"get-{unique_id}",
        created_by=SystemActor(),
        description="full body",
    )
    state = ExecutionState(
        task_id=f"tg-{unique_id}",
        context_id=f"ctxg-{unique_id}",
        user_id="test_user",
        session_id=f"flowg_{unique_id}:ctxg",
        branch_id="default",
    )
    detail = await _bound(work_item_get, builtin_tool_clients).run({"work_item_id": item.work_item_id}, state)
    assert detail["work_item_id"] == item.work_item_id
    assert detail["description"] == "full body"
    assert "assignment" in detail


async def test_work_item_create_missing_assignee_flow_id_raises(
    app, builtin_tool_clients, unique_id: str
) -> None:
    state = ExecutionState(
        task_id=f"t3-{unique_id}",
        context_id=f"ctx3-{unique_id}",
        user_id="test_user",
        session_id=f"flow3_{unique_id}:ctx3",
        branch_id="default",
    )
    with pytest.raises(ValueError):
        await _bound(work_item_create, builtin_tool_clients).run(
            {"title": "bad", "assignee_type": "agent"},
            state,
        )


async def test_work_item_complete_with_resolution(builtin_tool_clients, app, di, unique_id: str) -> None:
    item = await di.work_item_service.create(
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
    result = await _bound(work_item_complete, builtin_tool_clients).run(
        {
            "work_item_id": item.work_item_id,
            "resolution_text": "done via tool",
        },
        state,
    )
    assert result["state"] == WorkItemState.DONE.value


async def test_work_item_create_self_assigns_employee_of_session_flow(
    builtin_tool_clients,
    app, di, unique_id: str
) -> None:
    flow_id = f"self_flow_{unique_id}"
    await provision_flow_employee_for_tests(
        di=di,
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
        result = await _bound(work_item_create, builtin_tool_clients).run(
            {"title": f"self task {unique_id}", "assignee_type": "self"},
            state,
        )
        item = await WorkItem.require_in_company("system", result["work_item_id"])
        assert isinstance(item.assignment, UsersAssignment)
        assert item.assignment.user_ids == [flow_employee_user_id(flow_id)]
    finally:
        await cleanup_flow_employee_for_tests(di=di,flow_id=flow_id)


async def test_work_item_create_records_actor_created_by(
    builtin_tool_clients, app, unique_id: str
) -> None:
    state = ExecutionState(
        task_id=f"tc-{unique_id}",
        context_id=f"ctxc-{unique_id}",
        user_id="test_user",
        session_id=f"flowc_{unique_id}:ctxc",
        branch_id="default",
    )
    result = await _bound(work_item_create, builtin_tool_clients).run({"title": f"actor {unique_id}"}, state)
    item = await WorkItem.require_in_company("system", result["work_item_id"])
    assert item.created_by.actor_kind == ActorKind.USER
    assert isinstance(item.created_by, UserActor)
    assert item.created_by.user_id == "test_user"
    assert item.board_id is not None


async def test_work_item_create_user_and_unassigned(
    builtin_tool_clients, app, unique_id: str
) -> None:
    state = ExecutionState(
        task_id=f"tu-{unique_id}",
        context_id=f"ctxu-{unique_id}",
        user_id="test_user",
        session_id=f"flowu_{unique_id}:ctxu",
        branch_id="default",
    )
    human = await _bound(work_item_create, builtin_tool_clients).run(
        {"title": f"human {unique_id}", "assignee_type": "user", "assignee_user_id": "human_x"},
        state,
    )
    human_item = await WorkItem.require_in_company("system", human["work_item_id"])
    assert isinstance(human_item.assignment, UsersAssignment)
    assert human_item.assignment.user_ids == ["human_x"]

    none = await _bound(work_item_create, builtin_tool_clients).run(
        {"title": f"none {unique_id}", "assignee_type": "unassigned"},
        state,
    )
    none_item = await WorkItem.require_in_company("system", none["work_item_id"])
    assert isinstance(none_item.assignment, UnassignedAssignment)
    assert none_item.assignment.assignee_kind == AssigneeKind.UNASSIGNED
    assert none_item.board_id is not None


async def test_work_item_create_user_missing_id_raises(
    app, builtin_tool_clients, unique_id: str
) -> None:
    state = ExecutionState(
        task_id=f"te-{unique_id}",
        context_id=f"ctxe-{unique_id}",
        user_id="test_user",
        session_id=f"flowe_{unique_id}:ctxe",
        branch_id="default",
    )
    with pytest.raises(ValueError):
        await _bound(work_item_create, builtin_tool_clients).run({"title": "bad", "assignee_type": "user"}, state)
