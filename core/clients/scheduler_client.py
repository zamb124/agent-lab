"""Клиент единого scheduler API."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.pagination import OffsetPage
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
)


class SchedulerClient:
    """Типизированный клиент scheduler control-plane."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._service_client = service_client or ServiceClient()

    async def create_schedule(self, request: PlatformScheduleCreateRequest) -> PlatformScheduledTask:
        response = await self._service_client.post(
            "scheduler",
            "/scheduler/api/v1/schedules",
            json=request.model_dump(mode="json"),
        )
        return PlatformScheduledTask.model_validate(response)

    async def list_schedules(self, filters: PlatformScheduleFilter) -> OffsetPage[PlatformScheduledTask]:
        params = filters.model_dump(mode="json", exclude_none=True)
        response = await self._service_client.get(
            "scheduler",
            "/scheduler/api/v1/schedules",
            params=params,
        )
        return OffsetPage[PlatformScheduledTask].model_validate(response)

    async def get_schedule(self, schedule_task_id: str) -> PlatformScheduledTask:
        response = await self._service_client.get(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}",
        )
        return PlatformScheduledTask.model_validate(response)

    async def pause_schedule(self, schedule_task_id: str) -> PlatformScheduledTask:
        response = await self._service_client.post(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}/pause",
        )
        return PlatformScheduledTask.model_validate(response)

    async def resume_schedule(self, schedule_task_id: str) -> PlatformScheduledTask:
        response = await self._service_client.post(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}/resume",
        )
        return PlatformScheduledTask.model_validate(response)

    async def cancel_schedule(self, schedule_task_id: str) -> PlatformScheduledTask:
        response = await self._service_client.post(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}/cancel",
        )
        return PlatformScheduledTask.model_validate(response)

    async def run_schedule_now(self, schedule_task_id: str) -> PlatformScheduledTask:
        response = await self._service_client.post(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}/run-now",
        )
        return PlatformScheduledTask.model_validate(response)

    async def get_schedule_redis_snapshot(self, schedule_task_id: str) -> PlatformRedisScheduleSnapshot:
        response = await self._service_client.get(
            "scheduler",
            f"/scheduler/api/v1/schedules/{schedule_task_id}/redis",
        )
        return PlatformRedisScheduleSnapshot.model_validate(response)
