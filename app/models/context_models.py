"""
Модели контекста без зависимостей от frontend.
Используются в core/context.py для избежания циклических импортов.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from app.identity.models import User, Company

if TYPE_CHECKING:
    from app.core.state import State


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
    
    flow_variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Переменные flow",
        description="Переменные доступные во flow и агентах",
    )
    company_variables: Dict[str, Any] = Field(
        default_factory=dict,
        title="Переменные компании",
        description="Переменные компании для использования в промптах",
    )
    
    state: Optional[Dict[str, Any]] = Field(
        default=None,
        title="State агента",
        description="Ссылка на текущий state агента (доступен в тулах)",
    )
    
    class Config:
        arbitrary_types_allowed = True
