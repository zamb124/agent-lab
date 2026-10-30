"""Модели flow-расписаний: представление платформенного расписания для ExecutionState."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import Field

from core.models import FlexibleBaseModel
from core.scheduler.models import PlatformScheduleType, ScheduledTaskStatus
from core.types import JsonObject


class ContentType(str, Enum):
    """Тип контента задачи."""
    MESSAGE = "message"
    TOOL_CALL = "tool_call"


class ScheduledTaskInfo(FlexibleBaseModel):
    """Информация о scheduled task для ExecutionState."""

    schedule_task_id: str = Field(..., description="ID записи платформенного scheduler")
    schedule_id: str | None = Field(default=None, description="ID в RedisScheduleSource")
    flow_id: str = Field(..., description="ID агента")
    session_id: str = Field(..., description="ID сессии")
    user_id: str = Field(..., description="ID пользователя")

    schedule_type: PlatformScheduleType = Field(..., description="Тип расписания")
    content_type: ContentType = Field(..., description="Тип контента")

    # Конфигурация расписания
    cron: str | None = Field(default=None, description="Cron выражение")
    interval_minutes: int | None = Field(default=None, description="Интервал в минутах")
    run_at: datetime | None = Field(default=None, description="Время запуска (one_time)")

    # Контент
    content: str = Field(..., description="Сообщение или имя tool")
    tool_args: JsonObject | None = Field(default=None, description="Аргументы для tool_call")
    description: str | None = Field(default=None, description="Описание задачи")

    status: ScheduledTaskStatus = Field(default=ScheduledTaskStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = Field(default=None)
    next_run: datetime | None = Field(default=None, description="Следующий запуск")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке при FAILED")


__all__ = ["ContentType", "ScheduledTaskInfo"]
