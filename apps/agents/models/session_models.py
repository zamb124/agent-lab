"""
Модели для сессий (Session).
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

from core.fields import Field


class SessionStatus(str, Enum):
    """Статусы сессии"""

    ACTIVE = "active"
    PROCESSING = "processing"
    WAITING_INPUT = "waiting_input"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class SessionConfig(BaseModel):
    """Конфигурация сессии"""

    session_id: str = Field(
        title="ID сессии", description="Уникальный идентификатор сессии", readonly=True
    )
    platform: str = Field(
        title="Платформа",
        description="Платформа (telegram, api, web)",
    )
    user_id: str = Field(
        title="ID пользователя", description="Идентификатор пользователя"
    )
    flow_id: str = Field(title="ID флоу", description="Идентификатор флоу")
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        title="Статус",
        description="Статус сессии",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные сессии",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время создания сессии",
        readonly=True,
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        title="Последняя активность",
        description="Время последней активности",
        readonly=True,
    )
    message_count: int = Field(
        default=0,
        title="Количество сообщений",
        description="Общее количество сообщений в сессии",
    )
    first_message: Optional[str] = Field(
        default=None,
        title="Первое сообщение",
        description="Первое сообщение пользователя (превью)",
    )

    @property
    def session_key(self) -> str:
        key = self.session_id.split("_")[-1]
        return f"session:{self.platform}:{self.user_id}:{self.flow_id}:{key}"

