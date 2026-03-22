"""
Сервис для управления scheduled tasks.
"""

import datetime
import uuid
from typing import Any, Dict, List, Optional

from apps.flows.config import get_settings
from apps.flows.src.db.scheduled_task_repository import ScheduledTaskRepository
from apps.flows.src.tasks.scheduled_tasks import execute_scheduled_task
from core.logging import get_logger
from core.scheduler import get_schedule_source
from core.scheduler.models import (
    ContentType,
    ScheduledTaskInfo,
    ScheduledTaskStatus,
    ScheduleType,
)

logger = get_logger(__name__)


class ScheduleService:
    """Сервис для создания и управления scheduled tasks."""

    def __init__(self, scheduled_task_repository: ScheduledTaskRepository):
        self._repository = scheduled_task_repository
        self._settings = get_settings()

    async def _get_source(self):
        """Получает RedisScheduleSource."""
        source = get_schedule_source(self._settings.database.redis_url)
        await source.startup()
        return source

    async def schedule_cron_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        cron: str,
        content_type: ContentType,
        content: str,
        tool_args: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
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
        task_id = str(uuid.uuid4())
        
        task = ScheduledTaskInfo(
            id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            schedule_type=ScheduleType.CRON,
            content_type=content_type,
            cron=cron,
            content=content,
            tool_args=tool_args,
            description=description,
        )
        
        source = await self._get_source()
        
        schedule = await execute_scheduled_task.kicker().schedule_by_cron(
            source,
            cron,
            scheduled_task_id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            task_type=content_type.value,
            payload={
                "content": content,
                "tool_args": tool_args,
            },
        )
        
        task.schedule_id = schedule.schedule_id
        await self._repository.save(task)
        
        logger.info(f"Scheduled cron task created: id={task_id}, cron={cron}")
        return task

    async def schedule_interval_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        interval_minutes: int,
        content_type: ContentType,
        content: str,
        tool_args: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
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
        task_id = str(uuid.uuid4())
        
        task = ScheduledTaskInfo(
            id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            schedule_type=ScheduleType.INTERVAL,
            content_type=content_type,
            interval_minutes=interval_minutes,
            content=content,
            tool_args=tool_args,
            description=description,
        )
        
        source = await self._get_source()
        
        schedule = await execute_scheduled_task.kicker().schedule_by_interval(
            source,
            datetime.timedelta(minutes=interval_minutes),
            scheduled_task_id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            task_type=content_type.value,
            payload={
                "content": content,
                "tool_args": tool_args,
            },
        )
        
        task.schedule_id = schedule.schedule_id
        await self._repository.save(task)
        
        logger.info(f"Scheduled interval task created: id={task_id}, interval={interval_minutes}min")
        return task

    async def schedule_one_time_task(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        run_at: datetime.datetime,
        content_type: ContentType,
        content: str,
        tool_args: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
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
        task_id = str(uuid.uuid4())
        
        task = ScheduledTaskInfo(
            id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            schedule_type=ScheduleType.ONE_TIME,
            content_type=content_type,
            run_at=run_at,
            content=content,
            tool_args=tool_args,
            description=description,
            next_run=run_at,
        )
        
        source = await self._get_source()
        
        schedule = await execute_scheduled_task.kicker().schedule_by_time(
            source,
            run_at,
            scheduled_task_id=task_id,
            flow_id=flow_id,
            session_id=session_id,
            user_id=user_id,
            task_type=content_type.value,
            payload={
                "content": content,
                "tool_args": tool_args,
            },
        )
        
        task.schedule_id = schedule.schedule_id
        await self._repository.save(task)
        
        logger.info(f"Scheduled one-time task created: id={task_id}, run_at={run_at}")
        return task

    async def list_tasks(
        self,
        session_id: str,
        status: Optional[ScheduledTaskStatus] = None
    ) -> List[ScheduledTaskInfo]:
        """
        Получает список задач для сессии.
        
        Args:
            session_id: ID сессии
            status: Фильтр по статусу
            
        Returns:
            Список ScheduledTaskInfo
        """
        return await self._repository.get_by_session(session_id, status)

    async def cancel_task(self, task_id: str) -> bool:
        """
        Отменяет задачу.
        
        Args:
            task_id: ID задачи
            
        Returns:
            True если задача отменена
        """
        task = await self._repository.get_by_id(task_id)
        if not task:
            logger.warning(f"Task not found: id={task_id}")
            return False
        
        if task.status != ScheduledTaskStatus.PENDING:
            logger.warning(f"Task is not pending: id={task_id}, status={task.status}")
            return False
        
        if task.schedule_id:
            source = await self._get_source()
            await source.delete_schedule(task.schedule_id)
        
        await self._repository.update_status(task_id, ScheduledTaskStatus.CANCELLED)
        
        logger.info(f"Task cancelled: id={task_id}")
        return True

    async def get_task(self, task_id: str) -> Optional[ScheduledTaskInfo]:
        """Получает задачу по ID."""
        return await self._repository.get_by_id(task_id)

    async def mark_executed(self, task_id: str) -> bool:
        """Помечает задачу как выполненную."""
        return await self._repository.update_status(
            task_id,
            ScheduledTaskStatus.EXECUTED,
            executed_at=datetime.datetime.now(datetime.timezone.utc)
        )

