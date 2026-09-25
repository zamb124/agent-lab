"""Каталог команд Scheduler: `scheduler/schedule_tasks/*` для WS RPC и REST-зеркала."""

from __future__ import annotations

from apps.scheduler.di import SchedulerDi
from apps.scheduler.realtime.operations import (
    SchedulerTaskIdPayload,
    op_schedule_tasks_cancel,
    op_schedule_tasks_create,
    op_schedule_tasks_item,
    op_schedule_tasks_list,
    op_schedule_tasks_pause,
    op_schedule_tasks_redis_snapshot,
    op_schedule_tasks_resume,
    op_schedule_tasks_run_now,
)
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleFilter
from core.websocket import Operation, RegisteredOperation

SCHEDULER_OPERATIONS: dict[str, RegisteredOperation[SchedulerDi]] = {
    "scheduler/schedule_tasks/list_requested": Operation(
        payload_model=PlatformScheduleFilter, fn=op_schedule_tasks_list
    ),
    "scheduler/schedule_tasks/item_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_item
    ),
    "scheduler/schedule_tasks/create_requested": Operation(
        payload_model=PlatformScheduleCreateRequest, fn=op_schedule_tasks_create
    ),
    "scheduler/schedule_tasks/pause_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_pause
    ),
    "scheduler/schedule_tasks/resume_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_resume
    ),
    "scheduler/schedule_tasks/cancel_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_cancel
    ),
    "scheduler/schedule_tasks/run_now_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_run_now
    ),
    "scheduler/schedule_tasks/redis_snapshot_requested": Operation(
        payload_model=SchedulerTaskIdPayload, fn=op_schedule_tasks_redis_snapshot
    ),
}
