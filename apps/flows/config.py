"""
Конфигурация сервиса flows.

Расширяет BaseSettings полями, специфичными для flows и runtime.
"""

from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from core.config import BaseSettings
from core.config.loader import load_merged_config
from core.config.models import LLMConfig, S3Config
from core.config.models import PushConfig

FLOWS_PUBLIC_API_PREFIX = "/flows/api/v1"

# Потолок wall-clock (сек) для настроек: выше нельзя ни в conf.json, ни в ENV.
_FLOWS_WALL_TIME_HARD_MAX_SECONDS: int = 3600


class ExternalFlowConfig(BaseModel):
    """Внешний flow (A2A endpoint) для подключения при старте."""

    url: str = Field(..., description="Base URL удалённого flow (A2A)")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP-заголовки к внешнему агенту")
    name: str | None = Field(
        default=None,
        description="Отображаемое имя (если не задано — из A2A Agent Card удалённого endpoint)",
    )


class ExternalFlowsConfig(BaseModel):
    """Конфигурация реестра внешних flows (A2A endpoints)"""

    flows: list[ExternalFlowConfig] = Field(
        default_factory=list, description="Список внешних flows для инициализации"
    )
    health_check_interval: int = Field(
        default=60, description="Интервал проверки здоровья в секундах"
    )


def _default_push_config() -> PushConfig:
    """Push: VAPID и APNs; дефолты VAPID для локальной разработки flows."""
    return PushConfig(
        enabled=True,
        vapid_public_key="BJBAqLwOEE7A7gIDCXW7vzmEwh23-ug6-1qpiuotzwROEDX_ZiVUk2BO3_eINDqXxBvxG2uRfukXVVBse167BAM",
        vapid_private_key="n6oh3YpjV9APhmtdZ-p18P4YGLtBRLATLbprkXWAldA",
        vapid_email="admin@platform.local",
    )


class MockConfig(BaseModel):
    """Конфигурация глобальных моков"""

    enabled: bool = Field(default=False, description="Включен ли mock режим глобально")
    permission_groups: list[str] = Field(
        default_factory=lambda: ["admin", "developers"],
        description="Группы с правом использования mock через request metadata"
    )
    llm: dict[str, Any] | None = Field(
        default=None, description="Mock конфигурация для LLM (default_response или очередь)"
    )
    tools: dict[str, Any] = Field(
        default_factory=dict, description="Mock ответы для tools по имени"
    )
    flows: dict[str, Any] = Field(
        default_factory=dict, description="Mock ответы для flows по ID"
    )
    nodes: dict[str, Any] = Field(
        default_factory=dict, description="Mock данные для nodes по ID"
    )


class FlowSettings(BaseSettings):
    """
    Настройки сервиса flows.

    Наследуется от BaseSettings, добавляя поля для LLM, S3, внешних flows и т.д.
    Базовые поля (database, auth, logging и др.) — из родителя.
    """

    service_name: str = Field(default="flows", description="Имя сервиса")

    # Сервисные конфиги
    llm: LLMConfig = Field(default_factory=LLMConfig)
    s3: S3Config = Field(default_factory=S3Config)
    external_flows: ExternalFlowsConfig = Field(default_factory=ExternalFlowsConfig)
    mock: MockConfig = Field(default_factory=MockConfig)
    push: PushConfig = Field(default_factory=_default_push_config)

    cors_allow_origins: list[str] = Field(
        default_factory=list,
        description=(
            "Явные Origin для общего сервисного CORS (non-embed маршруты). "
            "Embed A2A CORS настраивается отдельно через embed-конфигурацию."
        ),
    )
    cors_allow_origin_regex: str | None = Field(
        default=None,
        description=(
            "Regex для разрешённого Origin. Если None и server.debug — в apps/flows/main.py "
            "подставляется dev-паттерн localhost и *.lvh.me."
        ),
    )
    dynamic_embed_cors_enabled: bool = Field(
        default=True,
        description="Включает dynamic CORS для /flows/api/v1/embed/{embed_id} по EmbedConfig.allowed_origins",
    )
    flow_execution_wall_time_cap_seconds: int = Field(
        default=3600,
        ge=1,
        le=_FLOWS_WALL_TIME_HARD_MAX_SECONDS,
        description=(
            "Верхняя граница таймаута run flow (и clamp для state): FlowConfig.timeout и дедлайн run не больше этого"
        ),
    )
    node_execution_wall_time_cap_seconds: int = Field(
        default=3600,
        ge=1,
        le=_FLOWS_WALL_TIME_HARD_MAX_SECONDS,
        description="Верхняя граница node_timeout_seconds у нод",
    )
    default_flow_timeout_seconds: int = Field(
        default=600,
        ge=1,
        le=_FLOWS_WALL_TIME_HARD_MAX_SECONDS,
        description=(
            "Wall-clock лимит выполнения одного run flow (сек), если в FlowConfig.timeout не задано; "
            "не больше flow_execution_wall_time_cap_seconds"
        ),
    )
    graph_max_iterations: int = Field(
        default=100,
        ge=1,
        le=1_000_000,
        description=(
            "Максимум итераций внешнего цикла графа за один Flow.run; верхняя граница NodeConfig.max_visits_per_run"
        ),
    )

    @model_validator(mode="after")
    def _default_flow_timeout_within_cap(self) -> Self:
        if self.default_flow_timeout_seconds > self.flow_execution_wall_time_cap_seconds:
            raise ValueError(
                "default_flow_timeout_seconds не больше flow_execution_wall_time_cap_seconds: "
                f"{self.default_flow_timeout_seconds} > {self.flow_execution_wall_time_cap_seconds}"
            )
        return self

    @model_validator(mode="after")
    def _public_http_prefix_must_be_flows(self) -> Self:
        """
        create_service_app вешает REST/WS на /{server.name}/api/...; фронт и
        фабрики всегда дергают /flows/api/... . Без этого совпадения GET
        /flows/api/v1/flows не попадает в API (часто из-за SERVER__NAME=core
        в окружении или дефолта ServerConfig) и отдаётся SPA-роут, который
        для сегмента api возвращает 404.
        """
        if self.server.name != "flows":
            object.__setattr__(
                self,
                "server",
                self.server.model_copy(update={"name": "flows"}),
            )
        return self


_settings: FlowSettings | None = None


def get_settings() -> FlowSettings:
    """
    Возвращает настройки сервиса flows.

    Собирает FlowSettings из merged config (service_name=flows) и регистрирует в core.
    Если core уже получил FlowSettings из create_service_app — переиспользует тот же объект.
    """
    global _settings
    if _settings is not None:
        return _settings
    from core.config import get_settings as core_get_settings
    from core.config import set_settings as core_set_settings

    core_candidate = core_get_settings()
    if isinstance(core_candidate, FlowSettings):
        _settings = core_candidate
        return _settings

    merged_config = load_merged_config(service_name="flows", silent=True)
    _settings = FlowSettings(**merged_config)
    core_set_settings(_settings)

    return _settings


def set_settings(new_settings: FlowSettings) -> None:
    """Устанавливает глобальный settings instance"""
    global _settings
    _settings = new_settings
    from core.config import set_settings as core_set_settings
    core_set_settings(new_settings)


def reset_settings():
    """Сбрасывает настройки (для тестов)"""
    global _settings
    _settings = None


class _SettingsProxy:
    """Proxy для доступа к актуальным настройкам."""

    def __getattr__(self, name):
        return getattr(get_settings(), name)

    def __repr__(self):
        return repr(get_settings())


settings = _SettingsProxy()

