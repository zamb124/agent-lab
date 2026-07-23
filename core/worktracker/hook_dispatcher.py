"""Helpers for WorkItem actor identity on bus events.

HTTP hook dispatcher удалён: wake/resume идут только через шину
`platform:events` (consumer group `flows`).
"""

from __future__ import annotations

from core.worktracker.models import (
    UserActor,
    WorkItem,
)

_PLATFORM_SYSTEM_HOOK_USER_ID = "platform-worktracker-system"


def hook_dispatch_internal_user_id(work_item: WorkItem) -> str:
    """user_id актора для meta/assigned_by при публикации событий назначения."""
    created_by = work_item.created_by
    if isinstance(created_by, UserActor):
        return created_by.user_id
    return _PLATFORM_SYSTEM_HOOK_USER_ID


__all__ = [
    "hook_dispatch_internal_user_id",
]
