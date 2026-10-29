"""Unit tests for WorktrackerClient and TeamClient."""

from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from apps.flows.tools.scheduling.scheduling import list_scheduled_tasks, schedule_cron_task
from apps.flows.tools.wiki.wiki_tools import (
    wiki_create_page,
    wiki_delete_page,
    wiki_list_tree,
    wiki_update_markdown,
)
from core.clients.team_client import TeamClient
from core.clients.worktracker_client import WorktrackerClient
from core.worktracker.models import UserActor, WorkItemState


@pytest.mark.asyncio
async def test_worktracker_client_get_returns_created_item(
    di: FlowsDi,
    unique_id: str,
) -> None:
    client = WorktrackerClient(di.work_item_service)
    created = await client.create_manual_task(
        company_id="system",
        title=f"get-{unique_id}",
        created_by=UserActor(user_id=f"user_{unique_id}"),
    )
    item = await client.get("system", created.work_item_id)
    assert item.work_item_id == created.work_item_id
    assert item.title == f"get-{unique_id}"


@pytest.mark.asyncio
async def test_worktracker_client_list_excludes_completed_item(
    di: FlowsDi,
    unique_id: str,
) -> None:
    client = WorktrackerClient(di.work_item_service)
    user_id = f"user_{unique_id}"
    created = await client.create_manual_task(
        company_id="system",
        title=f"list-{unique_id}",
        created_by=UserActor(user_id=user_id),
    )
    open_ids = {
        item.work_item_id
        for item in await client.list(
            "system",
            assignee_user_id=user_id,
            exclude_terminal=True,
        )
    }
    assert created.work_item_id in open_ids
    completion = await client.complete(
        company_id="system",
        work_item_id=created.work_item_id,
        terminal_state=WorkItemState.DONE,
    )
    assert completion.newly_terminal is True
    after_ids = {
        item.work_item_id
        for item in await client.list(
            "system",
            assignee_user_id=user_id,
            exclude_terminal=True,
        )
    }
    assert created.work_item_id not in after_ids


@pytest.mark.asyncio
async def test_worktracker_client_lists_created_queue_and_board(
    di: FlowsDi,
    unique_id: str,
) -> None:
    client = WorktrackerClient(di.work_item_service)
    user_id = f"user_{unique_id}"
    namespace = f"ns-{unique_id}"
    queue = await client.create_queue(
        company_id="system",
        name=f"Queue {unique_id}",
        slug=f"q-{unique_id}",
        creator=UserActor(user_id=user_id),
    )
    queue_ids = {item.work_queue_id for item in await client.list_queues("system", user_id=user_id)}
    assert queue.work_queue_id in queue_ids
    boards = await client.list_boards("system", namespace=namespace)
    assert [board.board_id for board in boards]
    assert all(board.company_id == "system" for board in boards)
    created = await client.create_manual_task(
        company_id="system",
        title=f"board-{unique_id}",
        created_by=UserActor(user_id=user_id),
        namespace=namespace,
    )
    assert created.board_id == boards[0].board_id


@pytest.mark.asyncio
async def test_team_client_resolve_requires_query() -> None:
    client = TeamClient()
    with pytest.raises(ValueError, match="query is required"):
        await client.resolve_user("   ", limit=5)


def test_wiki_and_scheduling_tool_effects_metadata() -> None:
    assert wiki_list_tree.effects == ["read"]
    assert wiki_create_page.effects == ["create"]
    assert wiki_create_page.confirmation_floor == "preview"
    assert wiki_update_markdown.effects == ["update"]
    assert wiki_delete_page.effects == ["delete"]
    assert wiki_delete_page.confirmation_floor == "approval"
    assert schedule_cron_task.effects == ["create"]
    assert schedule_cron_task.confirmation_floor == "preview"
    assert list_scheduled_tasks.effects == ["read"]
