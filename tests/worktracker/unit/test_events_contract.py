"""Контракт push-событий worktracker: имена не совпадают с командами."""

from __future__ import annotations

from core.worktracker.events import (
    WORK_ITEM_COMMENT_CREATED,
    WORK_ITEM_COMPLETED,
    WORK_ITEM_CREATED,
    WORK_ITEM_MOVED,
    WORK_ITEM_UPDATED,
)


def test_push_event_types_are_not_command_names() -> None:
    push_types = {
        WORK_ITEM_CREATED,
        WORK_ITEM_UPDATED,
        WORK_ITEM_MOVED,
        WORK_ITEM_COMPLETED,
        WORK_ITEM_COMMENT_CREATED,
    }
    for event_type in push_types:
        assert not event_type.endswith("_requested")
        assert "/work_item/" in event_type
