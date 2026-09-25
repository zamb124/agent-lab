"""Назначение задач flow-сотруднику: диспатч в inbox vs notify человеку.

Реальные worktracker + flows сервисы (`flows_service`), реальный Redis-listener.
Сотрудник — обычный `UsersAssignment` c `flow_employee_{flow_id}`; человек получает
уведомление, сотрудник — нет (его работа уходит в inbox flows).
"""

from __future__ import annotations

import pytest

from apps.flows.src.models import FlowConfig, FlowEmployeeConfig
from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
)
from core.models.identity_models import User
from core.worktracker.models import (
    ActorKind,
    SystemActor,
    UserActor,
    UsersAssignment,
    WorkItemKind,
    WorkItemState,
)

pytestmark = pytest.mark.asyncio

_NOTIFY_ASSIGNED = "notify/worktracker/work_item_assigned_received"


async def _provision_employee(flow_id: str, curator_id: str, di) -> str:
    """Сидит flow + сотрудника-агента в shared/flows БД, чтобы inbox-диспатч прошёл."""

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"Dispatch flow {flow_id}",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state):\n    return state",
            }
        },
        edges=[{"from_node": "main", "to_node": None}],
        employee=FlowEmployeeConfig(
            enabled=True, roles=["member"], curator_user_ids=[curator_id]
        ),
    )
    await FlowConfig.create_version(flow_config)
    await ensure_flow_employee(
        di,
        flow_id=flow_id,
        company_id="system",
        name=f"AI Worker {flow_id}",
        roles=["member"],
        curator_user_ids=[curator_id],
    )
    return flow_employee_user_id(flow_id)


async def _cleanup_employee(flow_id: str, di) -> None:

    await deactivate_flow_employee(di, flow_id=flow_id, company_id="system")
    await User.delete_by_id(flow_employee_user_id(flow_id))


async def test_human_assignment_notifies(
    app, flows_service, worktracker_service, platform_events_listener, unique_id
):
    _ = app, flows_service
    human_id = f"human_{unique_id}"
    item = await worktracker_service.create(
        company_id="system",
        title=f"human-{unique_id}",
        created_by=SystemActor(),
        assignment=UsersAssignment(user_ids=[human_id]),
    )
    events = await platform_events_listener(_NOTIFY_ASSIGNED, human_id, 3.0)
    assert any(e["payload"]["data"].get("work_item_id") == item.work_item_id for e in events)


async def test_employee_assignment_not_notified(
    app, flows_service, worktracker_service, platform_events_listener, unique_id, di
):
    _ = app, flows_service
    flow_id = f"disp_emp_{unique_id}"
    emp_id = await _provision_employee(flow_id, curator_id=f"cur_{unique_id}", di=di)
    try:
        item = await worktracker_service.create(
            company_id="system",
            title=f"emp-{unique_id}",
            created_by=SystemActor(),
            kind=WorkItemKind.AGENT_JOB,
            assignment=UsersAssignment(user_ids=[emp_id]),
        )
        # сотрудник-агент не получает human-нотификацию (его работа — в inbox flows)
        events = await platform_events_listener(_NOTIFY_ASSIGNED, emp_id, 2.0)
        assert events == []
        fetched = await worktracker_service.get("system", item.work_item_id)
        assert isinstance(fetched.assignment, UsersAssignment)
        assert fetched.assignment.user_ids == [emp_id]
    finally:
        await _cleanup_employee(flow_id, di=di)


async def test_mixed_assignment_notifies_only_human(
    app, flows_service, worktracker_service, platform_events_listener, unique_id, di
):
    _ = app, flows_service
    flow_id = f"disp_mix_{unique_id}"
    emp_id = await _provision_employee(flow_id, curator_id=f"cur_{unique_id}", di=di)
    human_id = f"human_mix_{unique_id}"
    try:
        await worktracker_service.create(
            company_id="system",
            title=f"mix-{unique_id}",
            created_by=SystemActor(),
            assignment=UsersAssignment(user_ids=[human_id, emp_id]),
        )
        human_events = await platform_events_listener(_NOTIFY_ASSIGNED, human_id, 3.0)
        assert len(human_events) >= 1
        emp_events = await platform_events_listener(_NOTIFY_ASSIGNED, emp_id, 1.0)
        assert emp_events == []
    finally:
        await _cleanup_employee(flow_id, di=di)


async def test_reassign_human_to_employee(
    app, flows_service, worktracker_service, unique_id, di
):
    _ = app, flows_service
    flow_id = f"disp_re_{unique_id}"
    emp_id = await _provision_employee(flow_id, curator_id=f"cur_{unique_id}", di=di)
    try:
        item = await worktracker_service.create(
            company_id="system",
            title=f"re-{unique_id}",
            created_by=SystemActor(),
            assignment=UsersAssignment(user_ids=[f"human_{unique_id}"]),
        )
        reassigned = await worktracker_service.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=UsersAssignment(user_ids=[emp_id]),
        )
        assert isinstance(reassigned.assignment, UsersAssignment)
        assert reassigned.assignment.user_ids == [emp_id]
    finally:
        await _cleanup_employee(flow_id, di=di)


async def test_repository_assignee_flow_id_filter(
    app, flows_service, worktracker_service, unique_id, di
):
    _ = app, flows_service
    flow_id = f"filter_flow_{unique_id}"
    emp_id = await _provision_employee(flow_id, curator_id=f"cur_{unique_id}", di=di)
    try:
        target = await worktracker_service.create(
            company_id="system",
            title=f"target-{unique_id}",
            created_by=SystemActor(),
            kind=WorkItemKind.AGENT_JOB,
            assignment=UsersAssignment(user_ids=[emp_id]),
        )
        other = await worktracker_service.create(
            company_id="system",
            title=f"other-{unique_id}",
            created_by=SystemActor(),
            assignment=UsersAssignment(user_ids=[f"human_{unique_id}"]),
        )
        listed = await worktracker_service.list("system", assignee_flow_id=flow_id, limit=100)
        ids = {i.work_item_id for i in listed}
        assert target.work_item_id in ids
        assert other.work_item_id not in ids
    finally:
        await _cleanup_employee(flow_id, di=di)


async def test_queue_member_is_user_actor(app, worktracker_service, unique_id):
    _ = app
    owner_id = f"owner_{unique_id}"
    queue = await worktracker_service.create_queue(
        company_id="system",
        name=f"Q {unique_id}",
        slug=f"disp-q-{unique_id}",
        creator=UserActor(user_id=owner_id),
    )
    emp_id = flow_employee_user_id(f"queue_flow_{unique_id}")
    member = await worktracker_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=emp_id),
        actor_user_id=owner_id,
    )
    assert member.member.actor_kind == ActorKind.USER
    assert isinstance(member.member, UserActor)
    assert member.member.user_id == emp_id
    members = await worktracker_service.list_queue_members(queue.work_queue_id)
    assert any(
        isinstance(m.member, UserActor) and m.member.user_id == emp_id for m in members
    )


async def test_completed_terminal_state(app, worktracker_service, unique_id):
    _ = app
    item = await worktracker_service.create(
        company_id="system",
        title=f"term-{unique_id}",
        created_by=SystemActor(),
    )
    completion = await worktracker_service.complete(
        company_id="system", work_item_id=item.work_item_id
    )
    assert completion.work_item.state == WorkItemState.DONE
