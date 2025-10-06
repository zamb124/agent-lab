"""
Модели контекста без зависимостей от frontend.
Используются в core/context.py для избежания циклических импортов.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from app.identity.models import User, Company


class Context(BaseModel):
    """Глобальный контекст запроса"""

    user: User = Field(
        title="Пользователь",
        description="Пользователь выполняющий запрос",
    )
    session_id: Optional[str] = Field(
        default=None,
        title="ID сессии", 
        description="Идентификатор сессии",
    )
    platform: str = Field(
        title="Платформа",
        description="Платформа откуда поступил запрос",
    )
    active_company: Optional[Company] = Field(
        default=None,
        title="Активная компания", 
        description="Текущая активная компания пользователя",
    )
    user_companies: List[Company] = Field(
        default_factory=list,
        title="Компании пользователя",
        description="Все доступные компании пользователя",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные контекста",
    )
