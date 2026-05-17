"""Сервис управления scheduled tasks через единый scheduler API."""

import datetime
import uuid
from typing import Any

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
    ScheduleType,
)

logger = get_logger(__name__)


class ScheduleService:
    """Сервис совместимости для tools scheduling в flows."""

    def __init__(
        self,
        scheduler_client: SchedulerClient,
        scheduler_service=None,
        scheduled_task_repository=None,
    ):
        self._scheduler_client = scheduler_client
        self._scheduler_service = scheduler_service
        self._scheduled_task_repository = scheduled_task_repository

    def _map_task(self, task: PlatformScheduledTask) -> ScheduledTaskInfo:
        payload = task.payload
        nested_payload = payload.get("payload")
        if not isinstance(nested_payload, dict):
            raise ValueError("scheduler payload must include nested payload dict")
        content = nested_payload.get("content")
        if not isinstance(content, str):
            raise ValueError("scheduler payload.content must be string")
        tool_args = nested_payload.get("tool_args")
        task_type = payload.get("task_type")
        if not isinstance(task_type, str):
            raise ValueError("scheduler payload.task_type must be string")
        flow_id = payload.get("flow_id")
        session_id = payload.get("session_id")
        user_id = payload.get("user_id")
        if not isinstance(flow_id, str):
            raise ValueError("scheduler payload.flow_id must be string")
        if not isinstance(session_id, str):
            raise ValueError("scheduler payload.session_id must be string")
        if not isinstance(user_id, str):
            raise ValueError("scheduler payload.user_id must be string")
        schedule_type_raw = task.schedule_type
        schedule_type = ScheduleType(
            schedule_type_raw.value if hasattr(schedule_type_raw, "value") else str(schedule_type_raw)
        )

        return ScheduledTaskInfo(
            id=task.id,
            schedule_id=task.schedule_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            schedule_type=schedule_type,
            content_type=ContentType(task_type),
            cron=task.cron,
            interval_minutes=int(task.interval_seconds / 60) if task.interval_seconds else None,
            run_at=task.run_at,
            content=content,
            tool_args=tool_args if isinstance(tool_args, dict) else None,
            description=None,
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
        tool_args: dict[str, Any] | None,
        cron: str | None = None,
        interval_seconds: int | None = None,
        run_at: datetime.datetime | None = None,
    ) -> ScheduledTaskInfo:
        flow_task_id = str(uuid.uuid4())
        payload = {
            "scheduled_task_id": flow_task_id,
            "flow_id": flow_id,
            "session_id": session_id,
            "user_id": user_id,
            "task_type": content_type.value,
            "payload": {
                "content": content,
                "tool_args": tool_args,
            },
        }
        request = PlatformScheduleCreateRequest(
            target_service="flows",
            task_name="execute_scheduled_task",
            queue_name="flows_worker",
            schedule_type=schedule_type,
            cron=cron,
            interval_seconds=interval_seconds,
            run_at=run_at,
            payload=payload,
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
        mapped = self._map_task(created)
        if self._scheduled_task_repository is not None:
            await self._scheduled_task_repository.save(mapped)
        return mapped

    async def schedule_cron_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        cron: str,
        content_type: ContentType,
        content: str,
        tool_args: dict[str, Any] | None = None,
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
            cron=cron,
        )
        logger.info(f"Scheduled cron task created via scheduler API: id={task.id}, cron={cron}")
        return task

    async def schedule_interval_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        interval_minutes: int,
        content_type: ContentType,
        content: str,
        tool_args: dict[str, Any] | None = None,
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
            interval_seconds=interval_minutes * 60,
        )
        logger.info(f"Scheduled interval task created via scheduler API: id={task.id}, interval={interval_minutes}min")
        return task

    async def schedule_one_time_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        run_at: datetime.datetime,
        content_type: ContentType,
        content: str,
        tool_args: dict[str, Any] | None = None,
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
            run_at=run_at,
        )
        logger.info(f"Scheduled one-time task created via scheduler API: id={task.id}, run_at={run_at}")
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
        filtered = []
        for item in task_items:
            item_session = item.payload.get("session_id")
            if item_session == session_id:
                filtered.append(self._map_task(item))
        return filtered

    async def cancel_task(self, task_id: str) -> bool:
        """
        Отменяет задачу.

        Args:
            task_id: ID задачи

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
                    schedule_task_id=task_id,
                )
            else:
                cancelled = await self._scheduler_client.cancel_schedule(task_id)
        except ValueError:
            return False
        logger.info(f"Task cancelled via scheduler API: id={cancelled.id}")
        if self._scheduled_task_repository is not None:
            await self._scheduled_task_repository.update_status(task_id, ScheduledTaskStatus.CANCELLED)
        return True

    async def get_task(self, task_id: str) -> ScheduledTaskInfo | None:
        """Получает задачу по ID."""
        if self._scheduler_service is not None:
            context = get_context()
            if context is None or context.active_company is None:
                raise ValueError("company context is required for scheduler service")
            task = await self._scheduler_service.get(
                company_id=context.active_company.company_id,
                schedule_task_id=task_id,
            )
        else:
            task = await self._scheduler_client.get_schedule(task_id)
        if task.target_service != "flows" or task.task_name != "execute_scheduled_task":
            raise ValueError(f"Task {task_id} is not flows scheduled task")
        return self._map_task(task)

    async def mark_executed(self, task_id: str) -> bool:
        """Помечает задачу как выполненную."""
        raise NotImplementedError("mark_executed is not supported in scheduler API mode")
