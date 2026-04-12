"""API управления платформенными расписаниями."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from core.pagination import OffsetPage
from apps.scheduler.dependencies import ContainerDep
from core.context import get_context
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduledTask,
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    ScheduledTaskStatus,
)

router = APIRouter(tags=["scheduler"])


def _company_id_from_context() -> str:
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=401, detail="Company context is required")
    return context.active_company.company_id


def _user_id_from_context() -> str:
    context = get_context()
    if context is None or context.user is None:
        raise HTTPException(status_code=401, detail="User context is required")
    return context.user.user_id


@router.post("/schedules", response_model=PlatformScheduledTask)
async def create_schedule(request: PlatformScheduleCreateRequest, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    user_id = _user_id_from_context()
    try:
        return await container.scheduler_service.create(company_id=company_id, user_id=user_id, request=request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/schedules", response_model=OffsetPage[PlatformScheduledTask])
async def list_schedules(
    container: ContainerDep,
    status: ScheduledTaskStatus | None = Query(default=None),
    target_service: str | None = Query(default=None),
    task_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> OffsetPage[PlatformScheduledTask]:
    company_id = _company_id_from_context()
    filters = PlatformScheduleFilter(
        status=status,
        target_service=target_service,
        task_name=task_name,
        limit=limit,
        offset=offset,
    )
    items, total = await asyncio.gather(
        container.scheduler_service.list(company_id=company_id, filters=filters),
        container.scheduler_service.count(company_id=company_id, filters=filters),
    )
    return OffsetPage[PlatformScheduledTask](items=items, total=total, limit=limit, offset=offset)


@router.get("/schedules/{schedule_task_id}", response_model=PlatformScheduledTask)
async def get_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.get(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/schedules/{schedule_task_id}/pause", response_model=PlatformScheduledTask)
async def pause_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.pause(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/schedules/{schedule_task_id}/resume", response_model=PlatformScheduledTask)
async def resume_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.resume(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/schedules/{schedule_task_id}/cancel", response_model=PlatformScheduledTask)
async def cancel_schedule(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.cancel(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/schedules/{schedule_task_id}/run-now", response_model=PlatformScheduledTask)
async def run_schedule_now(schedule_task_id: str, container: ContainerDep) -> PlatformScheduledTask:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.run_now(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/schedules/{schedule_task_id}/redis", response_model=PlatformRedisScheduleSnapshot)
async def get_schedule_redis_snapshot(schedule_task_id: str, container: ContainerDep) -> PlatformRedisScheduleSnapshot:
    company_id = _company_id_from_context()
    try:
        return await container.scheduler_service.get_redis_snapshot(
            company_id=company_id,
            schedule_task_id=schedule_task_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
