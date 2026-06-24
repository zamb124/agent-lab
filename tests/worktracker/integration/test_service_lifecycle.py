"""WorkItemService: lifecycle, state machine, delete."""

from __future__ import annotations

import pytest

from core.worktracker.models import (
    AgentAssignment,
    BoardColumn,
    QueueAssignment,
    SystemActor,
    UserActor,
    WorkItemResolution,
    WorkItemState,
)

pytestmark = pytest.mark.asyncio


async def test_update_each_field_independently(worktracker_service, unique_id: str) -> None:
    item = await worktracker_service.create_manual_task(
        company_id="system",
        title=f"upd-{unique_id}",
        created_by=SystemActor(),
    )
    updated = await worktracker_service.update(
        company_id="system",
        work_item_id=item.work_item_id,
        title=f"new-{unique_id}",
        description="desc",
        labels=["x"],
    )
    assert updated.title == f"new-{unique_id}"
    assert updated.description == "desc"
    assert updated.labels == ["x"]


async def test_delete_work_item(worktracker_service, worktracker_repository, unique_id: str) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"del-{unique_id}",
        created_by=SystemActor(),
    )
    deleted = await worktracker_service.delete(company_id="system", work_item_id=item.work_item_id)
    assert deleted is True
    with pytest.raises(ValueError):
        await worktracker_service.get("system", item.work_item_id)


async def test_reassign_terminal_forbidden(worktracker_service, unique_id: str) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"term-{unique_id}",
        created_by=SystemActor(),
    )
    await worktracker_service.complete(company_id="system", work_item_id=item.work_item_id)
    with pytest.raises(ValueError):
        await worktracker_service.reassign(
            company_id="system",
            work_item_id=item.work_item_id,
            assignment=AgentAssignment(flow_id="flow_x"),
        )


async def test_complete_idempotent(worktracker_service, unique_id: str) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"idem-{unique_id}",
        created_by=SystemActor(),
    )
    first = await worktracker_service.complete(
        company_id="system",
        work_item_id=item.work_item_id,
        resolution=WorkItemResolution(text="ok"),
    )
    assert first.newly_terminal is True
    second = await worktracker_service.complete(company_id="system", work_item_id=item.work_item_id)
    assert second.newly_terminal is False


async def test_cancel_and_reject_terminal_states(worktracker_service, unique_id: str) -> None:
    to_cancel = await worktracker_service.create(
        company_id="system",
        title=f"cancel-{unique_id}",
        created_by=SystemActor(),
    )
    cancelled = await worktracker_service.cancel(
        company_id="system", work_item_id=to_cancel.work_item_id
    )
    assert cancelled.work_item.state is WorkItemState.CANCELLED

    to_reject = await worktracker_service.create(
        company_id="system",
        title=f"reject-{unique_id}",
        created_by=SystemActor(),
    )
    rejected = await worktracker_service.reject(
        company_id="system",
        work_item_id=to_reject.work_item_id,
        reason="bad",
    )
    assert rejected.work_item.state is WorkItemState.FAILED


async def test_move_syncs_state_from_column(worktracker_service, unique_id: str) -> None:
    board = await worktracker_service.create_board(
        company_id="system",
        name=f"board-{unique_id}",
        columns=[
            BoardColumn(
                board_column_id="todo",
                label="To do",
                state=WorkItemState.OPEN,
                position=0,
            ),
            BoardColumn(
                board_column_id="doing",
                label="Doing",
                state=WorkItemState.IN_PROGRESS,
                position=1,
            ),
        ],
    )
    item = await worktracker_service.create(
        company_id="system",
        title=f"mv-{unique_id}",
        created_by=SystemActor(),
        board_id=board.board_id,
        board_column_id="todo",
    )
    moved = await worktracker_service.move(
        company_id="system",
        work_item_id=item.work_item_id,
        board_column_id="doing",
    )
    assert moved.state is WorkItemState.IN_PROGRESS


async def test_claim_only_unclaimed_queue_item(
    worktracker_service,
    unique_id: str,
) -> None:
    queue = await worktracker_service.create_queue(
        company_id="system",
        name="Ops",
        slug=f"ops-{unique_id}",
    )
    member = f"user_{unique_id}"
    await worktracker_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=member),
    )
    item = await worktracker_service.create(
        company_id="system",
        title=f"claim-{unique_id}",
        created_by=SystemActor(),
        assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
    )
    claimed = await worktracker_service.claim(
        company_id="system",
        work_item_id=item.work_item_id,
        user_id=member,
    )
    assert claimed.assignment.claimed_by_user_id == member
    assert claimed.state is WorkItemState.IN_PROGRESS
