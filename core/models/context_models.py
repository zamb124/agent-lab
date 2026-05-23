"""
Модели контекста без зависимостей от конкретных сервисов.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field

from core.models.base import StrictBaseModel
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.types import JsonObject, require_json_object


class Context(StrictBaseModel):
    """Глобальный контекст запроса с изолированными сервисами"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=True,
        validate_default=True,
        arbitrary_types_allowed=True,
    )

    user: User = Field(
        title="Пользователь",
        description="Пользователь выполняющий запрос",
    )
    host: str = Field(
        default="",
        title="Host",
        description="Host header из запроса (для построения URL)",
    )
    session_id: str | None = Field(
        default=None,
        title="ID сессии",
        description="Идентификатор сессии",
    )
    channel: str = Field(
        default="unknown",
        title="Канал",
        description="Канал откуда поступил запрос (a2a, telegram, whatsapp)",
    )
    flow_id: str | None = Field(
        default=None,
        title="ID агента",
        description="ID текущего агента",
    )
    active_company: Company | None = Field(
        default=None,
        title="Активная компания",
        description="Текущая активная компания пользователя",
    )
    user_companies: list[Company] = Field(
        default_factory=list,
        title="Компании пользователя",
        description="Все доступные компании пользователя",
    )
    active_namespace: str = Field(
        default="default",
        title="Активный namespace",
        description="Имя активного namespace (без префикса company_id)",
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные контекста",
    )
    language: Language = Field(
        default=Language.RU,
        title="Язык пользователя",
        description="Предпочитаемый язык интерфейса пользователя",
    )
    flow_variables: JsonObject = Field(
        default_factory=dict,
        title="Переменные flow",
        description="Переменные доступные во flow и агентах",
    )
    company_variables: JsonObject = Field(
        default_factory=dict,
        title="Переменные компании",
        description="Переменные компании для использования в промптах",
    )
    flow_config: JsonObject | None = Field(
        default=None,
        title="Конфигурация агента",
        description="FlowConfig для текущего запроса",
    )
    state: JsonObject | None = Field(
        default=None,
        title="Runtime state",
        description="Текущее runtime-состояние выполнения; не сериализуется между процессами.",
        exclude=True,
    )
    auth_token: str | None = Field(
        default=None,
        title="JWT токен",
        description="JWT токен для межсервисной авторизации (передается в HTTPRepositoryProxy)",
        exclude=True,
    )
    trace_id: str | None = Field(
        default=None,
        title="Trace ID",
        description="Идентификатор трассировки для межсервисного взаимодействия (формат: service:uuid)",
    )

    def to_dict(self) -> JsonObject:
        """
        Сериализует Context в dict для передачи через TaskIQ.

        Returns:
            Dict с данными контекста
        """
        return require_json_object(
            {
                "user": require_json_object(self.user.model_dump(mode="json"), "Context.user"),
                "active_company": (
                    require_json_object(
                        self.active_company.model_dump(mode="json"),
                        "Context.active_company",
                    )
                    if self.active_company
                    else None
                ),
                "user_companies": [
                    require_json_object(
                        company.model_dump(mode="json"),
                        "Context.user_companies[]",
                    )
                    for company in self.user_companies
                ],
                "session_id": self.session_id,
                "channel": self.channel,
                "flow_id": self.flow_id,
                "host": self.host,
                "flow_variables": self.flow_variables,
                "company_variables": self.company_variables,
                "metadata": self.metadata,
                "language": self.language.value,
                "trace_id": self.trace_id,
                "active_namespace": self.active_namespace,
                "auth_token": self.auth_token,
            },
            "Context",
        )

    @classmethod
    def from_dict(cls, data: JsonObject) -> "Context":
        """
        Восстанавливает Context из dict (после передачи через TaskIQ).

        Args:
            data: Dict с данными контекста

        Returns:
            Восстановленный Context
        """
        if data.get("user") is None:
            raise ValueError("Context.user is required")
        return cls.model_validate(data)
