"""
Базовая конфигурация приложения.
"""

import logging
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings as PydanticBaseSettings

from core.config.loader import load_merged_config

from core.config.models import (
    AuthConfig,
    CallsConfig,
    DatabaseConfig,
    ServerConfig,
    WorkerConfig,
    LoggingConfig,
    TelegramConfig,
    WhatsAppConfig,
    NanoBananaConfig,
    AmoCRMConfig,
    ProxyConfig,
    PaymentProvidersConfig,
    ProviderLitserveConfig,
    RAGConfig,
    SGRConfig,
    LegalConfig,
    TracingConfig,
    TasksConfig,
    CalendarSyncConfig,
    S3Config,
    LLMConfig,
    PushConfig,
    STTConfig,
)

logger = logging.getLogger(__name__)


class BaseSettings(PydanticBaseSettings):
    """
    Базовые настройки приложения.
    Наследуют все сервисы для добавления специфичных полей.
    
    Порядок приоритета (от низшего к высшему):
    1. Дефолты в коде
    2. base config.json
    3. service config.json
    4. env переменные
    """

    testing: bool = Field(default=False)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    provider_litserve: ProviderLitserveConfig = Field(default_factory=ProviderLitserveConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    s3: S3Config = Field(default_factory=S3Config)
    stt: STTConfig = Field(default_factory=STTConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    nano_banana: NanoBananaConfig = Field(default_factory=NanoBananaConfig)
    amocrm: AmoCRMConfig = Field(default_factory=AmoCRMConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    payment_providers: PaymentProvidersConfig = Field(default_factory=PaymentProvidersConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    sgr: SGRConfig = Field(default_factory=SGRConfig)
    legal: LegalConfig = Field(default_factory=LegalConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    calendar_sync: CalendarSyncConfig = Field(default_factory=CalendarSyncConfig)
    push: PushConfig = Field(default_factory=PushConfig)
    calls: CallsConfig = Field(default_factory=CallsConfig)
    recording_max_duration_seconds: float = Field(default=3600.0)

    model_config = ConfigDict(
        env_file=[".env"],
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="allow"
    )

    def __init__(self, **data):
        json_config = load_merged_config()
        merged_data = {**json_config, **data}
        super().__init__(**merged_data)



_settings_instance = None


def get_settings() -> BaseSettings:
    """Получает синглтон настроек"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = BaseSettings()
    return _settings_instance


def set_settings(new_settings: BaseSettings) -> None:
    """Устанавливает глобальный settings instance"""
    global _settings_instance
    _settings_instance = new_settings
    logger.info(f"Settings обновлены: env={new_settings.server.env}, port={new_settings.server.port}")


class _SettingsProxy:
    """
    Proxy для доступа к актуальным настройкам.
    Всегда делегирует к текущему _settings_instance через get_settings().
    Позволяет импортировать settings на уровне модуля и получать актуальные значения.
    """
    
    def __getattr__(self, name):
        return getattr(get_settings(), name)
    
    def __repr__(self):
        return repr(get_settings())
    
    def __str__(self):
        return str(get_settings())


settings = _SettingsProxy()

