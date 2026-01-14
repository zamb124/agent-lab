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
    host: str = Field(
        default="",
        title="Host",
        description="Host header из запроса (для построения URL)",
    )
    session_id: Optional[str] = Field(
        default=None,
        title="ID сессии",
        description="Идентификатор сессии",
    )
    channel: str = Field(
        title="Канал",
        description="Канал откуда поступил запрос (a2a, telegram, whatsapp)",
    )
    agent_id: Optional[str] = Field(
        default=None,
        title="ID агента",
        description="ID текущего агента",
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
    active_namespace: str = Field(
        default="default",
        title="Активный namespace",
        description="Имя активного namespace (без префикса company_id)",
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
    agent_config: Optional[Any] = Field(
        default=None,
        title="Конфигурация агента",
        description="AgentConfig для текущего запроса",
    )
    auth_token: Optional[str] = Field(
        default=None,
        title="JWT токен",
        description="JWT токен для межсервисной авторизации (передается в HTTPRepositoryProxy)",
        exclude=True,
    )
    trace_id: Optional[str] = Field(
        default=None,
        title="Trace ID",
        description="Идентификатор трассировки для межсервисного взаимодействия (формат: service:uuid)",
    )

    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    def to_dict(self) -> Dict[str, Any]:
        """
        Сериализует Context в dict для передачи через TaskIQ.
        
        Returns:
            Dict с данными контекста
        """
        return {
            "user": self.user.model_dump() if self.user else None,
            "active_company": self.active_company.model_dump() if self.active_company else None,
            "user_companies": [c.model_dump() for c in self.user_companies],
            "session_id": self.session_id,
            "channel": self.channel,
            "agent_id": self.agent_id,
            "host": self.host,
            "flow_variables": self.flow_variables,
            "company_variables": self.company_variables,
            "metadata": self.metadata,
            "language": self.language.value if self.language else "ru",
            "trace_id": self.trace_id,
            "active_namespace": self.active_namespace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Context":
        """
        Восстанавливает Context из dict (после передачи через TaskIQ).
        
        Args:
            data: Dict с данными контекста
            
        Returns:
            Восстановленный Context
        """
        user_data = data.get("user")
        active_company_data = data.get("active_company")
        user_companies_data = data.get("user_companies", [])
        
        return cls(
            user=User.model_validate(user_data) if user_data else None,
            active_company=Company.model_validate(active_company_data) if active_company_data else None,
            user_companies=[Company.model_validate(c) for c in user_companies_data],
            session_id=data.get("session_id"),
            channel=data.get("channel", "unknown"),
            agent_id=data.get("agent_id"),
            host=data.get("host", ""),
            flow_variables=data.get("flow_variables", {}),
            company_variables=data.get("company_variables", {}),
            metadata=data.get("metadata", {}),
            language=Language(data.get("language", "ru")),
            trace_id=data.get("trace_id"),
            active_namespace=data.get("active_namespace", "default"),
        )

