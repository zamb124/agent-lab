"""
Модель SessionConfig - конфигурация сессии.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import SessionStatus


class SessionConfig(BaseModel):
    """Конфигурация сессии"""

    model_config = ConfigDict(json_schema_extra={"storage_prefix": "session"})

    session_id: str = Field(..., description="Уникальный идентификатор сессии")
    channel: str = Field(..., description="Канал (a2a, telegram, api)")
    user_id: str = Field(..., description="Идентификатор пользователя")
    flow_id: str = Field(..., description="Идентификатор агента")
    context_id: str | None = Field(default=None, description="ID контекста (извлекается из session_id)")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Статус сессии")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Метаданные сессии")
    message_count: int = Field(default=0, description="Количество сообщений")
    first_message: str | None = Field(default=None, description="Первое сообщение пользователя")
    created_at: datetime | None = Field(default=None, description="Время создания")
    last_activity: datetime | None = Field(
        default=None, description="Время последней активности"
    )
