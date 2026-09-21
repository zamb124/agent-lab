"""REST-зеркало команд `scheduler/schedule_tasks/*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.scheduler.dependencies import ContainerDep
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
from core.context import require_context
from core.pagination import OffsetPage
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    ScheduledTaskStatus,
)

router = APIRouter(tags=["scheduler"])


@router.post("/schedules", response_model=PlatformScheduledTask)
async def create_schedule(
    request_body: PlatformScheduleCreateRequest, container: ContainerDep
) -> PlatformScheduledTask:
    return await op_schedule_tasks_create(
        request_body, user=require_context().user, container=container
    )


@router.get("/schedules", response_model=OffsetPage[PlatformScheduledTask])
async def list_schedules(
    container: ContainerDep,
    status: Annotated[ScheduledTaskStatus | None, Query()] = None,
    target_service: Annotated[str | None, Query()] = None,
    task_name: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[PlatformScheduledTask]:
    return await op_schedule_tasks_list(
        PlatformScheduleFilter(
            status=status,
            target_service=target_service,
            task_name=task_name,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/schedules/{schedule_task_id}", response_model=PlatformScheduledTask)
async def get_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await op_schedule_tasks_item(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )


@router.post("/schedules/{schedule_task_id}/pause", response_model=PlatformScheduledTask)
async def pause_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await op_schedule_tasks_pause(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )


@router.post("/schedules/{schedule_task_id}/resume", response_model=PlatformScheduledTask)
async def resume_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await op_schedule_tasks_resume(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )


@router.post("/schedules/{schedule_task_id}/cancel", response_model=PlatformScheduledTask)
async def cancel_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await op_schedule_tasks_cancel(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )


@router.post("/schedules/{schedule_task_id}/run-now", response_model=PlatformScheduledTask)
async def run_schedule_now(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await op_schedule_tasks_run_now(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )


@router.get("/schedules/{schedule_task_id}/redis", response_model=PlatformRedisScheduleSnapshot)
async def get_schedule_redis_snapshot(
    schedule_task_id: str, container: ContainerDep
) -> PlatformRedisScheduleSnapshot:
    return await op_schedule_tasks_redis_snapshot(
        SchedulerTaskIdPayload(schedule_task_id=schedule_task_id),
        user=require_context().user,
        container=container,
    )
