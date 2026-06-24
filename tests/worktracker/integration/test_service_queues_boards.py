"""WorkItemService: очереди, доски, members."""

from __future__ import annotations

import pytest

from core.worktracker.models import AgentActor, BoardColumn, UserActor, WorkItemState

pytestmark = pytest.mark.asyncio


async def test_create_queue_duplicate_slug_raises(worktracker_service, unique_id: str) -> None:
    slug = f"q-{unique_id}"
    await worktracker_service.create_queue(company_id="system", name="Q", slug=slug)
    with pytest.raises(ValueError):
        await worktracker_service.create_queue(company_id="system", name="Q2", slug=slug)


async def test_get_queue_by_slug(worktracker_service, unique_id: str) -> None:
    slug = f"slug-{unique_id}"
    created = await worktracker_service.create_queue(
        company_id="system",
        name="Queue",
        slug=slug,
    )
    fetched = await worktracker_service.get_queue_by_slug("system", slug)
    assert fetched.work_queue_id == created.work_queue_id


async def test_queue_members_and_is_member(worktracker_service, unique_id: str) -> None:
    queue = await worktracker_service.create_queue(
        company_id="system",
        name="Members",
        slug=f"m-{unique_id}",
    )
    user_id = f"user_{unique_id}"
    await worktracker_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=user_id),
    )
    assert await worktracker_service.is_member(queue.work_queue_id, UserActor(user_id=user_id))
    members = await worktracker_service.list_queue_members(queue.work_queue_id)
    assert len(members) == 1

    removed = await worktracker_service.remove_queue_member(
        work_queue_id=queue.work_queue_id,
        member=UserActor(user_id=user_id),
    )
    assert removed is True
    assert not await worktracker_service.is_member(queue.work_queue_id, UserActor(user_id=user_id))


async def test_add_agent_queue_member(worktracker_service, unique_id: str) -> None:
    queue = await worktracker_service.create_queue(
        company_id="system",
        name="Agents",
        slug=f"ag-{unique_id}",
    )
    flow_id = f"flow_{unique_id}"
    await worktracker_service.add_queue_member(
        company_id="system",
        work_queue_id=queue.work_queue_id,
        member=AgentActor(flow_id=flow_id),
        role="agent",
    )
    members = await worktracker_service.list_queue_members(queue.work_queue_id)
    assert any(isinstance(m.member, AgentActor) for m in members)


async def test_list_boards_by_namespace(worktracker_service, unique_id: str) -> None:
    namespace = f"ns-{unique_id}"
    board = await worktracker_service.create_board(
        company_id="system",
        name=f"Board {unique_id}",
        namespace=namespace,
        columns=[
            BoardColumn(
                board_column_id="todo",
                label="To do",
                state=WorkItemState.OPEN,
                position=0,
            ),
        ],
    )
    boards = await worktracker_service.list_boards("system", namespace=namespace)
    ids = {b.board_id for b in boards}
    assert board.board_id in ids


async def test_ensure_generic_board_idempotent(worktracker_service) -> None:
    first = await worktracker_service.ensure_generic_board("system")
    second = await worktracker_service.ensure_generic_board("system")
    assert first.board_id == second.board_id
