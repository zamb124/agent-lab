"""Push-события worktracker в Redis platform:ui_events."""

from __future__ import annotations

import pytest

from core.worktracker.events import (
    WORK_ITEM_COMMENT_CREATED,
    WORK_ITEM_COMPLETED,
    WORK_ITEM_CREATED,
    WORK_ITEM_MOVED,
    WORK_ITEM_UPDATED,
)
from core.worktracker.models import SystemActor
from tests.worktracker.helpers.redis_events import wait_work_item_event

pytestmark = pytest.mark.asyncio


async def test_create_publishes_created_event(
    worktracker_service,
    worktracker_ui_events_listener,
    unique_id: str,
) -> None:
    item = await worktracker_service.create_manual_task(
        company_id="system",
        title=f"rt-create-{unique_id}",
        created_by=SystemActor(),
    )
    event = await wait_work_item_event(
        worktracker_ui_events_listener,
        WORK_ITEM_CREATED,
        item.work_item_id,
    )
    assert event["type"] == WORK_ITEM_CREATED


async def test_update_publishes_updated_event(
    worktracker_service,
    worktracker_ui_events_listener,
    unique_id: str,
) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"rt-upd-{unique_id}",
        created_by=SystemActor(),
    )
    await worktracker_service.update(
        company_id="system",
        work_item_id=item.work_item_id,
        title=f"rt-upd-new-{unique_id}",
    )
    event = await wait_work_item_event(
        worktracker_ui_events_listener,
        WORK_ITEM_UPDATED,
        item.work_item_id,
    )
    assert event["type"] == WORK_ITEM_UPDATED


async def test_move_publishes_moved_event(
    worktracker_service,
    worktracker_ui_events_listener,
    worktracker_board,
    unique_id: str,
) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"rt-mv-{unique_id}",
        created_by=SystemActor(),
        board_id=worktracker_board.board_id,
        board_column_id="todo",
    )
    await worktracker_service.move(
        company_id="system",
        work_item_id=item.work_item_id,
        board_column_id="done",
    )
    event = await wait_work_item_event(
        worktracker_ui_events_listener,
        WORK_ITEM_MOVED,
        item.work_item_id,
    )
    assert event["type"] == WORK_ITEM_MOVED


async def test_complete_publishes_completed_event(
    worktracker_service,
    worktracker_ui_events_listener,
    unique_id: str,
) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"rt-done-{unique_id}",
        created_by=SystemActor(),
    )
    await worktracker_service.complete(company_id="system", work_item_id=item.work_item_id)
    event = await wait_work_item_event(
        worktracker_ui_events_listener,
        WORK_ITEM_COMPLETED,
        item.work_item_id,
    )
    assert event["type"] == WORK_ITEM_COMPLETED


async def test_comment_publishes_comment_created_event(
    worktracker_service,
    worktracker_ui_events_listener,
    unique_id: str,
) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"rt-cmt-{unique_id}",
        created_by=SystemActor(),
    )
    await worktracker_service.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=SystemActor(),
        text="hello",
    )
    events = await worktracker_ui_events_listener(WORK_ITEM_COMMENT_CREATED, None, 3.0)
    matching = [
        e
        for e in events
        if e.get("payload", {}).get("work_item_id") == item.work_item_id
    ]
    assert len(matching) >= 1
