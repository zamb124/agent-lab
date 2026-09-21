"""Каталог команд Scheduler: `scheduler/schedule_tasks/*` для WS RPC и REST-зеркала."""

from __future__ import annotations

from apps.scheduler.container import SchedulerContainer, get_scheduler_container
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
from core.logging import get_logger
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleFilter
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

SCHEDULER_OPERATIONS: dict[str, RegisteredOperation[SchedulerContainer]] = {
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


def register_scheduler_ws_commands() -> None:
    register_service_operations(SCHEDULER_OPERATIONS, get_scheduler_container)
    logger.info("command_router.registered", service="scheduler", operations=len(SCHEDULER_OPERATIONS))
