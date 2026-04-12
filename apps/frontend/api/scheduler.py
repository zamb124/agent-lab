"""API прокси для управления scheduler задачами из frontend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.pagination import OffsetPage
from apps.frontend.dependencies import ContainerDep
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    ScheduledTaskStatus,
)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.post("/schedules", response_model=PlatformScheduledTask)
async def create_schedule(request: PlatformScheduleCreateRequest, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.create_schedule(request)


@router.get("/schedules", response_model=OffsetPage[PlatformScheduledTask])
async def list_schedules(
    container: ContainerDep,
    status: ScheduledTaskStatus | None = Query(default=None),
    target_service: str | None = Query(default=None),
    task_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> OffsetPage[PlatformScheduledTask]:
    from core.scheduler.models import PlatformScheduleFilter

    return await container.scheduler_client.list_schedules(
        PlatformScheduleFilter(
            status=status,
            target_service=target_service,
            task_name=task_name,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/schedules/{schedule_task_id}", response_model=PlatformScheduledTask)
async def get_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.get_schedule(schedule_task_id)


@router.post("/schedules/{schedule_task_id}/pause", response_model=PlatformScheduledTask)
async def pause_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.pause_schedule(schedule_task_id)


@router.post("/schedules/{schedule_task_id}/resume", response_model=PlatformScheduledTask)
async def resume_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.resume_schedule(schedule_task_id)


@router.post("/schedules/{schedule_task_id}/cancel", response_model=PlatformScheduledTask)
async def cancel_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.cancel_schedule(schedule_task_id)


@router.post("/schedules/{schedule_task_id}/run-now", response_model=PlatformScheduledTask)
async def run_now_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    return await container.scheduler_client.run_schedule_now(schedule_task_id)


@router.get("/schedules/{schedule_task_id}/redis", response_model=PlatformRedisScheduleSnapshot)
async def get_schedule_redis_snapshot(schedule_task_id: str, container: ContainerDep) -> PlatformRedisScheduleSnapshot:
    return await container.scheduler_client.get_schedule_redis_snapshot(schedule_task_id)
