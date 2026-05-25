"""Сервис управления scheduled tasks через единый scheduler API."""

import datetime

from apps.flows.src.models.scheduled_task_payload import FlowScheduledTaskPayload
from core.clients.scheduler_client import SchedulerClient
from core.context import get_context
from core.logging import get_logger
from core.scheduler.models import (
    ContentType,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskInfo,
    ScheduledTaskStatus,
)
from core.scheduler.service import SchedulerService
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)


class ScheduleService:
    """Сервис scheduling для flows.

    Source of truth — платформенный scheduler control-plane
    (``core.scheduler.SchedulerService`` + таблица ``scheduler_tasks``
    в shared БД).
    """

    def __init__(
        self,
        scheduler_client: SchedulerClient,
        scheduler_service: SchedulerService | None = None,
    ) -> None:
        self._scheduler_client: SchedulerClient = scheduler_client
        self._scheduler_service: SchedulerService | None = scheduler_service

    def _map_task(self, task: PlatformScheduledTask) -> ScheduledTaskInfo:
        payload = FlowScheduledTaskPayload.model_validate(task.payload)
        schedule_type = PlatformScheduleType(task.schedule_type)

        return ScheduledTaskInfo(
            schedule_task_id=task.schedule_task_id,
            schedule_id=task.schedule_id,
            flow_id=payload.flow_id,
            session_id=payload.session_id,
            user_id=payload.user_id,
            schedule_type=schedule_type,
            content_type=payload.content_type,
            cron=task.cron,
            interval_minutes=int(task.interval_seconds / 60) if task.interval_seconds else None,
            run_at=task.run_at,
            content=payload.content,
            tool_args=payload.tool_args,
            description=payload.description,
            status=task.status,
            created_at=task.created_at,
            executed_at=task.last_run_at,
            next_run=task.next_run_at,
            error_message=task.error_message,
        )

    async def _create_scheduler_task(
        self,
        *,
        schedule_type: PlatformScheduleType,
        flow_id: str,
        session_id: str,
        user_id: str,
        content_type: ContentType,
        content: str,
        tool_args: JsonObject | None,
        description: str | None = None,
        cron: str | None = None,
        interval_seconds: int | None = None,
        run_at: datetime.datetime | None = None,
    ) -> ScheduledTaskInfo:
        payload = FlowScheduledTaskPayload(
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
        )
        request = PlatformScheduleCreateRequest(
            target_service="flows",
            task_name="execute_scheduled_task",
            queue_name="flows_worker",
            schedule_type=schedule_type,
            cron=cron,
            interval_seconds=interval_seconds,
            run_at=run_at,
            payload=parse_json_object(
                payload.model_dump_json(exclude_none=True),
                "FlowScheduledTaskPayload",
            ),
        )
        if self._scheduler_service is not None:
            context = get_context()
            if context is None or context.active_company is None:
                raise ValueError("company context is required for scheduler service")
            created = await self._scheduler_service.create(
                company_id=context.active_company.company_id,
                user_id=user_id,
                request=request,
            )
        else:
            created = await self._scheduler_client.create_schedule(request)
        return self._map_task(created)

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
        """
        Создает периодическую задачу по cron расписанию.

        Args:
            flow_id: ID агента
            session_id: ID сессии
            user_id: ID пользователя
            cron: Cron выражение (например "0 10 * * *")
            content_type: Тип контента (message/tool_call)
            content: Сообщение или имя tool
            tool_args: Аргументы для tool_call
            description: Описание задачи

        Returns:
            ScheduledTaskInfo
        """
        task = await self._create_scheduler_task(
            schedule_type=PlatformScheduleType.CRON,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
            cron=cron,
        )
        logger.info(
            "Scheduled cron task created via scheduler API: schedule_task_id=%s, cron=%s",
            task.schedule_task_id,
            cron,
        )
        return task

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
        """
        Создает периодическую задачу с интервалом.

        Args:
            flow_id: ID агента
            session_id: ID сессии
            user_id: ID пользователя
            interval_minutes: Интервал в минутах
            content_type: Тип контента (message/tool_call)
            content: Сообщение или имя tool
            tool_args: Аргументы для tool_call
            description: Описание задачи

        Returns:
            ScheduledTaskInfo
        """
        task = await self._create_scheduler_task(
            schedule_type=PlatformScheduleType.INTERVAL,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
            interval_seconds=interval_minutes * 60,
        )
        logger.info(
            "Scheduled interval task created via scheduler API: schedule_task_id=%s, interval=%smin",
            task.schedule_task_id,
            interval_minutes,
        )
        return task

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
        """
        Создает одноразовую задачу на конкретное время.

        Args:
            flow_id: ID агента
            session_id: ID сессии
            user_id: ID пользователя
            run_at: Время запуска (datetime с timezone)
            content_type: Тип контента (message/tool_call)
            content: Сообщение или имя tool
            tool_args: Аргументы для tool_call
            description: Описание задачи

        Returns:
            ScheduledTaskInfo
        """
        task = await self._create_scheduler_task(
            schedule_type=PlatformScheduleType.ONE_TIME,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            content_type=content_type,
            content=content,
            tool_args=tool_args,
            description=description,
            run_at=run_at,
        )
        logger.info(
            "Scheduled one-time task created via scheduler API: schedule_task_id=%s, run_at=%s",
            task.schedule_task_id,
            run_at,
        )
        return task

    async def list_tasks(
        self,
        session_id: str,
        status: ScheduledTaskStatus | None = None
    ) -> list[ScheduledTaskInfo]:
        """
        Получает список задач для сессии.

        Args:
            session_id: ID сессии
            status: Фильтр по статусу

        Returns:
            Список ScheduledTaskInfo
        """
        if self._scheduler_service is not None:
            context = get_context()
            if context is None or context.active_company is None:
                raise ValueError("company context is required for scheduler service")
            task_items = await self._scheduler_service.list(
                company_id=context.active_company.company_id,
                filters=PlatformScheduleFilter(
                    status=status,
                    target_service="flows",
                    task_name="execute_scheduled_task",
                    limit=500,
                    offset=0,
                ),
            )
        else:
            tasks_page = await self._scheduler_client.list_schedules(
                PlatformScheduleFilter(
                    status=status,
                    target_service="flows",
                    task_name="execute_scheduled_task",
                    limit=500,
                    offset=0,
                )
            )
            task_items = tasks_page.items
        filtered: list[ScheduledTaskInfo] = []
        for item in task_items:
            item_payload = FlowScheduledTaskPayload.model_validate(item.payload)
            if item_payload.session_id == session_id:
                filtered.append(self._map_task(item))
        return filtered

    async def cancel_task(self, schedule_task_id: str) -> bool:
        """
        Отменяет задачу.

        Args:
            schedule_task_id: ID записи платформенного scheduler

        Returns:
            True если задача отменена
        """
        try:
            if self._scheduler_service is not None:
                context = get_context()
                if context is None or context.active_company is None:
                    raise ValueError("company context is required for scheduler service")
                cancelled = await self._scheduler_service.cancel(
                    company_id=context.active_company.company_id,
                    schedule_task_id=schedule_task_id,
                )
            else:
                cancelled = await self._scheduler_client.cancel_schedule(schedule_task_id)
        except ValueError:
            return False
        logger.info(
            "Task cancelled via scheduler API: schedule_task_id=%s",
            cancelled.schedule_task_id,
        )
        return True

    async def get_task(self, schedule_task_id: str) -> ScheduledTaskInfo | None:
        """Получает задачу по schedule_task_id."""
        if self._scheduler_service is not None:
            context = get_context()
            if context is None or context.active_company is None:
                raise ValueError("company context is required for scheduler service")
            task = await self._scheduler_service.get(
                company_id=context.active_company.company_id,
                schedule_task_id=schedule_task_id,
            )
        else:
            task = await self._scheduler_client.get_schedule(schedule_task_id)
        if task.target_service != "flows" or task.task_name != "execute_scheduled_task":
            raise ValueError(f"Task {schedule_task_id} is not flows scheduled task")
        return self._map_task(task)

    async def mark_executed(self, schedule_task_id: str) -> bool:
        """Помечает задачу как выполненную."""
        raise NotImplementedError(
            f"mark_executed is not supported in scheduler API mode: {schedule_task_id}"
        )
