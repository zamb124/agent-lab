"""
Конфигурация сервиса flows.

Расширяет BaseSettings полями, специфичными для flows и runtime.
"""

from typing import Optional, Dict, List
from pydantic import BaseModel, Field

from core.config import BaseSettings
from core.config.loader import load_merged_config
from core.config.models import LLMConfig, PushConfig as CorePushConfig, S3Config


class ExternalFlowConfig(BaseModel):
    """Внешний flow (A2A endpoint) для подключения при старте."""

    url: str = Field(..., description="Base URL удалённого flow (A2A)")
    auth_headers: Dict[str, str] = Field(default_factory=dict, description="Заголовки авторизации")
    name: Optional[str] = Field(
        default=None,
        description="Отображаемое имя (если не задано — из A2A Agent Card удалённого endpoint)",
    )


class ExternalFlowsConfig(BaseModel):
    """Конфигурация реестра внешних flows (A2A endpoints)"""

    flows: List[ExternalFlowConfig] = Field(
        default_factory=list, description="Список внешних flows для инициализации"
    )
    health_check_interval: int = Field(
        default=60, description="Интервал проверки здоровья в секундах"
    )


class PushConfig(CorePushConfig):
    """Push: VAPID и APNs; дефолты VAPID для локальной разработки flows."""

    enabled: bool = Field(default=True, description="Включить push уведомления")
    vapid_public_key: str = Field(
        default="BJBAqLwOEE7A7gIDCXW7vzmEwh23-ug6-1qpiuotzwROEDX_ZiVUk2BO3_eINDqXxBvxG2uRfukXVVBse167BAM",
        description="VAPID публичный ключ (URL-safe Base64)",
    )
    vapid_private_key: str = Field(
        default="n6oh3YpjV9APhmtdZ-p18P4YGLtBRLATLbprkXWAldA",
        description="VAPID приватный ключ (URL-safe Base64)",
    )
    vapid_email: str = Field(
        default="admin@platform.local",
        description="Контакт для VAPID sub claim (без префикса mailto:)",
    )


class MockConfig(BaseModel):
    """Конфигурация глобальных моков"""

    enabled: bool = Field(default=False, description="Включен ли mock режим глобально")
    permission_groups: List[str] = Field(
        default_factory=lambda: ["admin", "developers"],
        description="Группы с правом использования mock через request metadata"
    )
    llm: Optional[dict] = Field(
        default=None, description="Mock конфигурация для LLM (default_response или очередь)"
    )
    tools: dict = Field(
        default_factory=dict, description="Mock ответы для tools по имени"
    )
    flows: dict = Field(
        default_factory=dict, description="Mock ответы для flows по ID"
    )
    nodes: dict = Field(
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
    push: PushConfig = Field(default_factory=PushConfig)

    cors_allow_origins: List[str] = Field(
        default_factory=list,
        description=(
            "Явные Origin для CORS (embed/A2A с fetch credentials или Authorization). "
            "Прод: домены партнёрских сайтов. См. также cors_allow_origin_regex."
        ),
    )
    cors_allow_origin_regex: Optional[str] = Field(
        default=None,
        description=(
            "Regex для разрешённого Origin. Если None и server.debug — в apps/flows/main.py "
            "подставляется dev-паттерн localhost и *.lvh.me."
        ),
    )


_settings: Optional[FlowSettings] = None


def get_settings() -> FlowSettings:
    """
    Возвращает настройки сервиса flows.

    Собирает FlowSettings из merged config (service_name=flows) и регистрирует в core.
    """
    global _settings
    if _settings is None:
        from core.config import set_settings as core_set_settings
        
        merged_config = load_merged_config(service_name="flows")
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


