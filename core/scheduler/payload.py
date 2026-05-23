"""Helpers for scheduler task payload compatibility."""

from __future__ import annotations

from typing import Any

SCHEDULE_TASK_ID_KWARG = "schedule_task_id"
LEGACY_SCHEDULER_TASK_ID_KWARG = "scheduler_task_id"

_MISSING = object()


def normalize_schedule_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return scheduler payload with the canonical schedule_task_id kwarg."""
    normalized = dict(payload)
    legacy_value = normalized.pop(LEGACY_SCHEDULER_TASK_ID_KWARG, _MISSING)
    if SCHEDULE_TASK_ID_KWARG not in normalized and legacy_value is not _MISSING:
        normalized[SCHEDULE_TASK_ID_KWARG] = legacy_value
    return normalized
