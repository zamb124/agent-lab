"""
Модели контекста без зависимостей от frontend.
Используются в core/context.py для избежания циклических импортов.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from app.identity.models import User, Company
from app.models.i18n_models import Language

if TYPE_CHECKING:
    from app.core.state import State
    from app.models.core_models import FlowConfig, AgentConfig


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
        description="FlowConfig для текущего запроса (устанавливается в API/TaskProcessor/Interface)",
    )
    
    agent_config: Optional[Any] = Field(
        default=None,
        title="Конфигурация агента",
        description="AgentConfig для текущего запроса (устанавливается при выполнении агента)",
    )
    
    @field_validator('flow_config', mode='before')
    @classmethod
    def validate_flow_config(cls, v):
        """Преобразует dict в FlowConfig если нужно"""
        if v is None or not isinstance(v, dict):
            return v
        from app.models.core_models import FlowConfig
        return FlowConfig(**v)
    
    @field_validator('agent_config', mode='before')
    @classmethod
    def validate_agent_config(cls, v):
        """Преобразует dict в AgentConfig если нужно"""
        if v is None or not isinstance(v, dict):
            return v
        from app.models.core_models import AgentConfig
        return AgentConfig(**v)
    
    class Config:
        arbitrary_types_allowed = True
