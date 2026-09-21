"""Unit tests for WorktrackerClient and Team/Device clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.flows.src.clients.device_client import DeviceClient
from apps.flows.src.clients.team_client import TeamClient
from apps.flows.src.clients.worktracker_client import WorktrackerClient
from apps.flows.tools.scheduling.scheduling import list_scheduled_tasks, schedule_cron_task
from apps.flows.tools.wiki.wiki_tools import (
    wiki_create_page,
    wiki_delete_page,
    wiki_list_tree,
    wiki_update_markdown,
)
from core.worktracker.models import UserActor, WorkItemPriority, WorkItemState


@pytest.mark.asyncio
async def test_worktracker_client_delegates_get() -> None:
    service = MagicMock()
    service.get = AsyncMock(return_value=MagicMock(work_item_id="wi_1"))
    client = WorktrackerClient(service)
    item = await client.get("company_a", "wi_1")
    service.get.assert_awaited_once_with("company_a", "wi_1")
    assert item.work_item_id == "wi_1"


@pytest.mark.asyncio
async def test_worktracker_client_delegates_list_and_complete() -> None:
    service = MagicMock()
    service.list = AsyncMock(return_value=[])
    service.complete = AsyncMock(return_value=MagicMock(newly_terminal=True))
    client = WorktrackerClient(service)
    items = await client.list("c1", assignee_user_id="u1", exclude_terminal=True)
    assert items == []
    service.list.assert_awaited_once()
    completion = await client.complete(
        company_id="c1",
        work_item_id="wi_2",
        terminal_state=WorkItemState.DONE,
    )
    assert completion.newly_terminal is True
    service.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_worktracker_client_delegates_queue_and_board() -> None:
    service = MagicMock()
    service.list_queues = AsyncMock(return_value=[])
    service.list_boards = AsyncMock(return_value=[])
    service.create_manual_task = AsyncMock(return_value=MagicMock(work_item_id="wi_3"))
    client = WorktrackerClient(service)
    assert await client.list_queues("c1", user_id="u1") == []
    service.list_queues.assert_awaited_once_with("c1", user_id="u1")
    assert await client.list_boards("c1", namespace=None) == []
    created = await client.create_manual_task(
        company_id="c1",
        title="t",
        created_by=UserActor(user_id="u1"),
        priority=WorkItemPriority.NORMAL,
    )
    assert created.work_item_id == "wi_3"


@pytest.mark.asyncio
async def test_team_client_resolve_requires_query() -> None:
    client = TeamClient(
        company_repository=MagicMock(),
        user_repository=MagicMock(),
    )
    with pytest.raises(ValueError, match="query обязателен"):
        await client.resolve_user("   ", limit=5)


@pytest.mark.asyncio
async def test_device_client_tools_list_delegates() -> None:
    redis_client = MagicMock()
    client = DeviceClient(redis_client)
    send = AsyncMock(return_value={"tools": []})
    with patch(
        "apps.flows.src.clients.device_client.send_mcp_request_to_device",
        send,
    ):
        result = await client.tools_list("dev_1", timeout_seconds=10.0)
    assert result == {"tools": []}
    send.assert_awaited_once_with(
        redis_client,
        "dev_1",
        method="tools/list",
        params={},
        timeout_seconds=10.0,
    )


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
