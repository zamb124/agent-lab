"""Команды Scheduler: расписания компании (один `op_*` на verb)."""

from __future__ import annotations

import asyncio

from pydantic import Field

from apps.scheduler.di import Di
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.request_scope import require_company_admin, require_company_viewer
from core.scheduler import SchedulerService
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
)
from core.websocket import raise_invalid, raise_not_found


class SchedulerTaskIdPayload(StrictBaseModel):
    schedule_task_id: str = Field(min_length=1)


async def _require_task(
    scheduler_service: SchedulerService, company_id: str, schedule_task_id: str
) -> PlatformScheduledTask:
    try:
        return await scheduler_service.get(company_id=company_id, schedule_task_id=schedule_task_id)
    except ValueError as exc:
        raise_not_found(exc)


async def op_schedule_tasks_create(
    payload: PlatformScheduleCreateRequest,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    scope = await require_company_admin(di.authz_service)
    try:
        return await di.scheduler_service.create(
            company_id=scope.company_id, user_id=user.user_id, request=payload
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_schedule_tasks_list(
    payload: PlatformScheduleFilter,
    *,
    user: User,
    di: Di,
) -> OffsetPage[PlatformScheduledTask]:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    items, total = await asyncio.gather(
        di.scheduler_service.list(company_id=scope.company_id, filters=payload),
        PlatformScheduledTask.count(company_id=scope.company_id, filters=payload),
    )
    return OffsetPage[PlatformScheduledTask](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_schedule_tasks_item(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    _ = user
    scope = await require_company_viewer(di.authz_service)
    return await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)


async def op_schedule_tasks_pause(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    _ = user
    scope = await require_company_admin(di.authz_service)
    _ = await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)
    try:
        return await di.scheduler_service.pause(
            company_id=scope.company_id, schedule_task_id=payload.schedule_task_id
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_schedule_tasks_resume(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    _ = user
    scope = await require_company_admin(di.authz_service)
    _ = await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)
    try:
        return await di.scheduler_service.resume(
            company_id=scope.company_id, schedule_task_id=payload.schedule_task_id
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_schedule_tasks_cancel(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    _ = user
    scope = await require_company_admin(di.authz_service)
    _ = await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)
    try:
        return await di.scheduler_service.cancel(
            company_id=scope.company_id, schedule_task_id=payload.schedule_task_id
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_schedule_tasks_run_now(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformScheduledTask:
    _ = user
    scope = await require_company_admin(di.authz_service)
    _ = await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)
    try:
        return await di.scheduler_service.run_now(
            company_id=scope.company_id, schedule_task_id=payload.schedule_task_id
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_schedule_tasks_redis_snapshot(
    payload: SchedulerTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> PlatformRedisScheduleSnapshot:
    """Состояние записи в RedisScheduleSource — диагностика расхождений с БД."""
    _ = user
    scope = await require_company_viewer(di.authz_service)
    _ = await _require_task(di.scheduler_service, scope.company_id, payload.schedule_task_id)
    try:
        return await di.scheduler_service.get_redis_snapshot(
            company_id=scope.company_id, schedule_task_id=payload.schedule_task_id
        )
    except ValueError as exc:
        raise_invalid(exc)
