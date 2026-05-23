"""
Контракт лог-записи платформы.

Каждая запись, проходящая через core.logging, нормализуется до этой схемы
независимо от выбранного renderer (JSON или console). Поля совместимы с
OpenTelemetry semantic conventions, чтобы логи можно было собирать любым
коллектором без переименований.

Никаких фолбеков: если значение неизвестно — поле отсутствует, не None.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]
DeploymentEnvironment = Literal["local", "test", "production"]


class LogServiceFields(BaseModel):
    """Идентификация сервиса (всегда присутствует)."""

    name: str = Field(description="Имя сервиса процесса (flows, crm, sync, *_worker, scheduler)")
    version: str | None = Field(
        default=None,
        description="Версия деплоя (settings.server.deployment_version), если задана",
    )
    environment: DeploymentEnvironment = Field(description="local, test или production")


class LogHttpFields(BaseModel):
    """HTTP-семантика OTel."""

    method: str = Field(description="HTTP метод (GET, POST, ...)")
    route: str = Field(description="Шаблон маршрута, если резолвится; иначе path")
    status_code: int | None = Field(default=None, description="HTTP статус ответа")
    duration_ms: float | None = Field(default=None, description="Длительность запроса")
    request_size: int | None = Field(default=None)
    response_size: int | None = Field(default=None)
    user_agent: str | None = Field(default=None)
    client_ip: str | None = Field(default=None)


class LogTaskFields(BaseModel):
    """TaskIQ-задача."""

    id: str = Field(description="task_id из TaskiqMessage")
    name: str = Field(description="полное имя task функции")
    queue: str = Field(description="имя очереди (Redis Stream)")
    duration_ms: float | None = Field(default=None)
    retry: int | None = Field(default=None)


class LogExceptionFields(BaseModel):
    """Структурированная информация об исключении."""

    type: str
    message: str
    stacktrace: str | None = Field(default=None)


class LogRecordPayload(BaseModel):
    """
    Каноничная форма записи. Используется для документации и валидации в тестах.

    Реальные записи формируются процессорами structlog по этим именам ключей,
    но не сериализуются через Pydantic в hot-path (для производительности).
    """

    timestamp: str = Field(description="ISO 8601 в UTC")
    level: LogLevel
    logger: str = Field(description="dotted name, например apps.crm.services.entity_service")
    message: str = Field(description="Человеческий текст без интерполяции значений")

    service: LogServiceFields

    request_id: str | None = Field(default=None, description="UUID одного HTTP/WS запроса")
    trace_id: str | None = Field(default=None, description="OTel trace_id 32 hex или service:uuid")
    span_id: str | None = Field(default=None, description="OTel span_id 16 hex")

    user_id: str | None = Field(default=None)
    company_id: str | None = Field(default=None)
    company_subdomain: str | None = Field(default=None)
    session_id: str | None = Field(default=None)
    namespace: str | None = Field(default=None)

    http: LogHttpFields | None = Field(default=None)
    task: LogTaskFields | None = Field(default=None)

    event: str | None = Field(
        default=None,
        description="Стабильное имя события, например http_request, task_started, llm_call",
    )

    exception: LogExceptionFields | None = Field(default=None)

    attributes: dict[str, object] = Field(
        default_factory=dict,
        description="Произвольные доменные поля; имена должны браться из core.logging.attributes",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


REQUIRED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"timestamp", "level", "logger", "message", "service"}
)
"""Ключи, без которых запись считается невалидной (используется в тестах)."""


REDACT_PLACEHOLDER = "[REDACTED]"
"""Подстановка для значений, попавших в drop_keys конфига."""


class LoggingMisconfigured(RuntimeError):
    """Конфигурация логирования невалидна — процесс не должен подниматься."""
