"""
Модели для системы скедулера.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field

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
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ScheduledTaskInfo(FlexibleBaseModel):
    """Информация о scheduled task для ExecutionState."""
    
    id: str = Field(..., description="ID задачи")
    schedule_id: Optional[str] = Field(default=None, description="ID в RedisScheduleSource")
    agent_id: str = Field(..., description="ID агента")
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


__all__ = [
    "ScheduleType",
    "ContentType",
    "ScheduledTaskStatus",
    "ScheduledTaskInfo",
]

