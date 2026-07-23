"""Назначение исполнителя публикует доменное событие на шину `platform:events`.

Wake-up flow-сотрудника идёт не через `WorkItemHook`, а через событие
`worktracker/work_item/assigned` (consumer group `flows` → EmployeeInboxService).
Здесь проверяется публикация события на create/reassign.
"""

from __future__ import annotations

import pytest

from core.identity.flow_employee import flow_employee_user_id
from core.worktracker.events import WORK_ITEM_ASSIGNED
from core.worktracker.models import (
    SystemActor,
    UsersAssignment,
    WorkItemKind,
)
from tests.fixtures.flow_employee_test_helpers import (
    cleanup_flow_employee_for_tests,
    provision_flow_employee_for_tests,
)

pytestmark = pytest.mark.asyncio


def _assigned_events_for_item(events: list[dict], work_item_id: str) -> list[dict]:
    matched: list[dict] = []
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        work_item = payload.get("work_item")
        if isinstance(work_item, dict) and work_item.get("work_item_id") == work_item_id:
            matched.append(event)
    return matched


async def test_create_with_assignment_publishes_assigned_event(
    app,
    flows_service,
    worktracker_service,
    platform_events_listener,
    unique_id: str,
) -> None:
    _ = app, flows_service
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
        )
        events = await platform_events_listener(WORK_ITEM_ASSIGNED, None, 3.0)
        matched = _assigned_events_for_item(events, item.work_item_id)
        assert matched, "ожидалось событие worktracker/work_item/assigned на шине"
        event_payload = matched[0]["payload"]
        assignment = event_payload["work_item"]["assignment"]
        assert assignment["user_ids"] == [flow_employee_user_id(flow_id)]
        # чисто доменное событие: без UI-доставки
        assert matched[0].get("delivery") is None
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)


async def test_reassign_publishes_assigned_event(
    app,
    flows_service,
    worktracker_service,
    platform_events_listener,
    unique_id: str,
) -> None:
    _ = app, flows_service
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
        )
        reassigned = await worktracker_service.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=UsersAssignment(user_ids=[flow_employee_user_id(flow_id)]),
        )
        assert isinstance(reassigned.assignment, UsersAssignment)
        events = await platform_events_listener(WORK_ITEM_ASSIGNED, None, 3.0)
        matched = _assigned_events_for_item(events, item.work_item_id)
        assert matched, "ожидалось событие worktracker/work_item/assigned после reassign"
    finally:
        await cleanup_flow_employee_for_tests(flow_id=flow_id)
