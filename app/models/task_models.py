"""
Модели для задач (Task).
"""

from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

from ..fields import Field


class TaskStatus(str, Enum):
    """Статусы задач"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_INPUT = "waiting_for_input"


class TaskConfig(BaseModel):
    """Конфигурация задачи"""

    class Config:
        storage_prefix = "task"

    task_id: str = Field(
        title="ID задачи", description="Уникальный идентификатор задачи", readonly=True
    )
    flow_id: str = Field(title="ID флоу", description="Идентификатор флоу для задачи")
    context: Any = Field(
        title="Контекст",
        description="Контекст выполнения задачи",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        title="Статус",
        description="Статус выполнения задачи",
    )
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        title="Входные данные",
        description="Входные данные для задачи",
    )
    output_data: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Выходные данные",
        description="Результат выполнения задачи",
        readonly=True,
    )
    error_message: Optional[str] = Field(
        default=None,
        title="Сообщение об ошибке",
        description="Сообщение об ошибке при выполнении",
        readonly=True,
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время создания задачи",
        readonly=True,
    )
    started_at: Optional[datetime] = Field(
        default=None,
        title="Запущено",
        description="Время начала выполнения",
        readonly=True,
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        title="Завершено",
        description="Время завершения выполнения",
        readonly=True,
    )
    
    @field_validator('context', mode='before')
    @classmethod
    def validate_context(cls, v):
        """Преобразует dict в Context если нужно"""
        if v is None or not isinstance(v, dict):
            return v
        from .context_models import Context
        return Context(**v)

    @property
    def user_id(self) -> str:
        return self.context.user.user_id

    @property
    def session_id(self) -> str:
        return self.context.session_id or ""

    @property
    def platform(self) -> str:
        return self.context.platform

