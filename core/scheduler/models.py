"""Модели для платформенного scheduler."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field, field_validator, model_validator

from core.models import FlexibleBaseModel


class ScheduleType(str, Enum):
    """Тип расписания задачи."""
    CRON = "cron"
    INTERVAL = "interval"
    ONE_TIME = "one_time"


class ContentType(str, Enum):
    """Тип контента задачи."""
    MESSAGE = "message"
    TOOL_CALL = "tool_call"


class ScheduledTaskStatus(str, Enum):
    """Статус scheduled task."""
    PENDING = "pending"
    PAUSED = "paused"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ScheduledTaskInfo(FlexibleBaseModel):
    """Информация о scheduled task для ExecutionState."""

    schedule_task_id: str = Field(..., description="ID записи платформенного scheduler")
    schedule_id: Optional[str] = Field(default=None, description="ID в RedisScheduleSource")
    flow_id: str = Field(..., description="ID агента")
    session_id: str = Field(..., description="ID сессии")
    user_id: str = Field(..., description="ID пользователя")

    schedule_type: ScheduleType = Field(..., description="Тип расписания")
    content_type: ContentType = Field(..., description="Тип контента")

    # Конфигурация расписания
    cron: Optional[str] = Field(default=None, description="Cron выражение")
    interval_minutes: Optional[int] = Field(default=None, description="Интервал в минутах")
    run_at: Optional[datetime] = Field(default=None, description="Время запуска (one_time)")

    # Контент
    content: str = Field(..., description="Сообщение или имя tool")
    tool_args: Optional[Dict[str, Any]] = Field(default=None, description="Аргументы для tool_call")
    description: Optional[str] = Field(default=None, description="Описание задачи")

    status: ScheduledTaskStatus = Field(default=ScheduledTaskStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = Field(default=None)
    next_run: Optional[datetime] = Field(default=None, description="Следующий запуск")
    error_message: Optional[str] = Field(default=None, description="Сообщение об ошибке при FAILED")


class PlatformScheduleType(str, Enum):
    """Тип расписания в платформенном API."""

    CRON = "cron"
    INTERVAL = "interval"
    ONE_TIME = "one_time"


class PlatformScheduleCreateRequest(FlexibleBaseModel):
    """Запрос на создание расписания."""

    target_service: str = Field(..., min_length=1, description="Сервис-назначение task")
    task_name: str = Field(..., min_length=1, description="Полное имя taskiq task")
    queue_name: Optional[str] = Field(default=None, description="Очередь broker (если нужна)")
    schedule_type: PlatformScheduleType = Field(..., description="Тип расписания")
    cron: Optional[str] = Field(default=None, description="Cron expression")
    interval_seconds: Optional[int] = Field(default=None, ge=1, description="Интервал в секундах")
    run_at: Optional[datetime] = Field(default=None, description="Время запуска для one-time")
    timezone: str = Field(default="UTC", min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict, description="kwargs для задачи")

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "PlatformScheduleCreateRequest":
        if self.schedule_type == PlatformScheduleType.CRON:
            if not self.cron:
                raise ValueError("cron is required for schedule_type=cron")
            return self
        if self.schedule_type == PlatformScheduleType.INTERVAL:
            if self.interval_seconds is None:
                raise ValueError("interval_seconds is required for schedule_type=interval")
            return self
        if self.run_at is None:
            raise ValueError("run_at is required for schedule_type=one_time")
        return self

    @field_validator("run_at")
    @classmethod
    def validate_run_at_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("run_at must be timezone-aware")
        return value


class PlatformScheduleUpdateStatusRequest(FlexibleBaseModel):
    """Запрос на смену состояния расписания."""

    reason: Optional[str] = Field(default=None, description="Причина операции")


class PlatformScheduleFilter(FlexibleBaseModel):
    """Фильтры списка расписаний."""

    status: Optional[ScheduledTaskStatus] = Field(default=None)
    target_service: Optional[str] = Field(default=None)
    task_name: Optional[str] = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PlatformScheduledTask(FlexibleBaseModel):
    """Сущность расписания платформенного scheduler."""

    schedule_task_id: str
    company_id: str
    schedule_id: Optional[str] = None
    target_service: str
    task_name: str
    queue_name: Optional[str] = None
    schedule_type: PlatformScheduleType
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    run_at: Optional[datetime] = None
    timezone: str = "UTC"
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ScheduledTaskStatus = ScheduledTaskStatus.PENDING
    created_by_user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def next_run_for_interval(self) -> datetime:
        if self.interval_seconds is None:
            raise ValueError("interval_seconds is required for interval schedules")
        return datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)


class PlatformRedisScheduleSnapshot(FlexibleBaseModel):
    """Снимок расписания из Redis schedule source."""

    schedule_task_id: str
    company_id: str
    schedule_id: Optional[str] = None
    exists_in_redis: bool
    status: ScheduledTaskStatus
    task_name: str
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    run_at: Optional[datetime] = None
    taskiq_task_id: Optional[str] = None
    kwargs: Dict[str, Any] = Field(default_factory=dict)
    labels: Dict[str, Any] = Field(default_factory=dict)
    missing_reason: Optional[str] = None


__all__ = [
    "ScheduleType",
    "ContentType",
    "ScheduledTaskStatus",
    "ScheduledTaskInfo",
    "PlatformScheduleType",
    "PlatformScheduleCreateRequest",
    "PlatformScheduleUpdateStatusRequest",
    "PlatformScheduleFilter",
    "PlatformScheduledTask",
    "PlatformRedisScheduleSnapshot",
]
