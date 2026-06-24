"""Summary и фильтры count/list WorkItem через worktracker_service."""

from __future__ import annotations

import pytest

from core.worktracker.models import (
    QueueAssignment,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
)

pytestmark = pytest.mark.asyncio


async def test_mine_summary_assigned_and_queue_inbox(
    worktracker_service,
    unique_id: str,
) -> None:
    company_id = "system"
    user_id = f"user_{unique_id}"
    queue = await worktracker_service.create_queue(
        company_id=company_id,
        name=f"Queue {unique_id}",
        slug=f"q-{unique_id}",
    )
    await worktracker_service.add_queue_member(
        company_id=company_id,
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=user_id),
        role="member",
    )
    assigned = await worktracker_service.create(
        company_id=company_id,
        title=f"Assigned {unique_id}",
        created_by=UserActor(user_id=user_id),
        assignment=UsersAssignment(user_ids=[user_id]),
    )
    _ = await worktracker_service.create(
        company_id=company_id,
        title=f"Queue item {unique_id}",
        created_by=UserActor(user_id=user_id),
        assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
    )
    _ = await worktracker_service.create(
        company_id=company_id,
        title=f"Other {unique_id}",
        created_by=UserActor(user_id=user_id),
        assignment=UnassignedAssignment(),
    )

    summary = await worktracker_service.mine_summary(company_id, user_id)
    assert summary.assigned_open_count >= 1
    assert summary.queue_inbox_count >= 1

    total_assigned = await worktracker_service.count(
        company_id,
        assignee_user_id=user_id,
        exclude_terminal=True,
    )
    assert total_assigned == summary.assigned_open_count

    _ = await worktracker_service.complete(
        company_id=company_id,
        work_item_id=assigned.work_item_id,
    )
    summary_after = await worktracker_service.mine_summary(company_id, user_id)
    assert summary_after.assigned_open_count == summary.assigned_open_count - 1


async def test_count_respects_work_queue_filter(worktracker_service, unique_id: str) -> None:
    company_id = "system"
    user_id = f"user_cnt_{unique_id}"
    queue_a = await worktracker_service.create_queue(
        company_id=company_id,
        name=f"A {unique_id}",
        slug=f"a-{unique_id}",
    )
    queue_b = await worktracker_service.create_queue(
        company_id=company_id,
        name=f"B {unique_id}",
        slug=f"b-{unique_id}",
    )
    _ = await worktracker_service.create(
        company_id=company_id,
        title=f"In A {unique_id}",
        created_by=UserActor(user_id=user_id),
        assignment=QueueAssignment(work_queue_id=queue_a.work_queue_id),
    )
    _ = await worktracker_service.create(
        company_id=company_id,
        title=f"In B {unique_id}",
        created_by=UserActor(user_id=user_id),
        assignment=QueueAssignment(work_queue_id=queue_b.work_queue_id),
    )

    count_a = await worktracker_service.count(
        company_id,
        work_queue_id=queue_a.work_queue_id,
        exclude_terminal=True,
    )
    assert count_a == 1
