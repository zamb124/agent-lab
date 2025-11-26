"""
Модели контекста без зависимостей от конкретных сервисов.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List

from core.fields import Field
from core.models.identity_models import User, Company
from core.models.i18n_models import Language


class Context(BaseModel):
    """Глобальный контекст запроса с изолированными сервисами"""

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
    language: Language = Field(
        default=Language.RU,
        title="Язык пользователя",
        description="Предпочитаемый язык интерфейса пользователя",
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
    flow_config: Optional[Any] = Field(
        default=None,
        title="Конфигурация flow",
        description="FlowConfig для текущего запроса",
    )
    agent_config: Optional[Any] = Field(
        default=None,
        title="Конфигурация агента",
        description="AgentConfig для текущего запроса",
    )
    interface: Optional[Any] = Field(
        default=None,
        title="Интерфейс",
        description="Интерфейс для отправки промежуточных сообщений",
        exclude=True,
    )
    container: Optional[Any] = Field(
        default=None,
        title="Container",
        description="Контейнер с изолированными сервисами",
        exclude=True,
    )

    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

