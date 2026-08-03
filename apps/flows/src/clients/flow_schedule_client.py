"""FlowScheduleClient — flow-scoped schedules over ScheduleService."""

from __future__ import annotations

import datetime

from apps.flows.src.container_state import require_current_container
from apps.flows.src.services.schedule_service import ScheduleService
from core.scheduler.models import ContentType, ScheduledTaskInfo, ScheduledTaskStatus
from core.types import JsonObject


class FlowScheduleClient:
    """Создание/список/отмена scheduled tasks для flow session."""

    _service: ScheduleService

    def __init__(self, service: ScheduleService | None = None) -> None:
        self._service = (
            service if service is not None else require_current_container().schedule_service
        )

    async def schedule_cron_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        cron: str,
        content_type: ContentType,
        content: str,
        tool_args: JsonObject | None = None,
        description: str | None = None,
    ) -> ScheduledTaskInfo:
        return await self._service.schedule_cron_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            cron=cron,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
        )

    async def schedule_interval_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        interval_minutes: int,
        content_type: ContentType,
        content: str,
        tool_args: JsonObject | None = None,
        description: str | None = None,
    ) -> ScheduledTaskInfo:
        return await self._service.schedule_interval_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            interval_minutes=interval_minutes,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
        )

    async def schedule_one_time_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        run_at: datetime.datetime,
        content_type: ContentType,
        content: str,
        tool_args: JsonObject | None = None,
        description: str | None = None,
    ) -> ScheduledTaskInfo:
        return await self._service.schedule_one_time_task(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            run_at=run_at,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
        )

    async def list_tasks(
        self,
        session_id: str,
        status: ScheduledTaskStatus | None = None,
    ) -> list[ScheduledTaskInfo]:
        return await self._service.list_tasks(session_id=session_id, status=status)

    async def cancel_task(self, schedule_task_id: str) -> bool:
        return await self._service.cancel_task(schedule_task_id)
