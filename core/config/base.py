"""
Базовая конфигурация приложения.
"""

from typing import ClassVar, Self, override

from pydantic import Field, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import PydanticBaseSettingsSource, SettingsConfigDict

from core.config.loader import load_merged_config
from core.config.models import (
    AuthConfig,
    BillingConfig,
    CalendarSyncConfig,
    CallsConfig,
    DatabaseConfig,
    LegalConfig,
    LLMConfig,
    LoggingConfig,
    MediaTranscriberConfig,
    NanoBananaConfig,
    PaymentProvidersConfig,
    ProviderLitserveConfig,
    ProxyConfig,
    PublicSiteConfig,
    PushConfig,
    RAGConfig,
    S3Config,
    ServerConfig,
    SGRConfig,
    SpeechProvidersConfig,
    TasksConfig,
    TelegramConfig,
    TextTransformsConfig,
    TracingConfig,
    WhatsAppConfig,
    WorkerConfig,
)
from core.llm_context.models import LLMContextConfig
from core.logging import get_logger
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)


class MergedJsonConfigSettingsSource(PydanticBaseSettingsSource):
    """Источник Pydantic Settings на основе объединённого JSON-конфига проекта."""

    @override
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[JsonValue | None, str, bool]:
        _ = field
        return None, field_name, False

    @override
    def __call__(self) -> JsonObject:
        return load_merged_config(silent=True)


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
    llm_context: LLMContextConfig = Field(default_factory=LLMContextConfig)
    text_transforms: TextTransformsConfig = Field(default_factory=TextTransformsConfig)
    provider_litserve: ProviderLitserveConfig = Field(default_factory=ProviderLitserveConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    s3: S3Config = Field(default_factory=S3Config)
    voice: SpeechProvidersConfig = Field(default_factory=SpeechProvidersConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    nano_banana: NanoBananaConfig = Field(default_factory=NanoBananaConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    payment_providers: PaymentProvidersConfig = Field(default_factory=PaymentProvidersConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    sgr: SGRConfig = Field(default_factory=SGRConfig)
    legal: LegalConfig = Field(default_factory=LegalConfig)
    public_site: PublicSiteConfig = Field(default_factory=PublicSiteConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    calendar_sync: CalendarSyncConfig = Field(default_factory=CalendarSyncConfig)
    push: PushConfig = Field(default_factory=PushConfig)
    calls: CallsConfig = Field(default_factory=CallsConfig)
    media_transcriber: MediaTranscriberConfig = Field(default_factory=MediaTranscriberConfig)
    recording_max_duration_seconds: float = Field(default=3600.0)
    transcribe_audio_redis_lock_ttl_seconds: int = Field(
        default=600,
        ge=60,
        description="TTL Redis SET NX для ключа sync:transcribe_audio:{company_id}:{message_id}.",
    )
    ws_presence_heartbeat_interval_seconds: float = Field(
        default=45.0,
        ge=5.0,
        description="Интервал продления ключа sync:ws:presence при открытом /sync/ws.",
    )
    ws_presence_ttl_seconds: int = Field(
        default=120,
        ge=30,
        description="TTL Redis ключа sync:ws:presence:{user_id}.",
    )
    sync_taskiq_wait_result_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        description="Таймаут task.wait_result для команд Sync из HTTP и /sync/ws.",
    )

    @model_validator(mode="after")
    def _ws_presence_ttl_vs_heartbeat(self) -> Self:
        min_ttl = int(2 * self.ws_presence_heartbeat_interval_seconds) + 1
        if self.ws_presence_ttl_seconds < min_ttl:
            raise ValueError(
                f"ws_presence_ttl_seconds ({self.ws_presence_ttl_seconds}) должен быть >= {min_ttl} (удвоенный heartbeat + 1 с)."
            )
        return self

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[".env"],
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="allow",
    )

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[PydanticBaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        _ = cls
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            MergedJsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

_settings_instance: BaseSettings | None = None

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
    logger.info(
        "settings.updated",
        env=new_settings.server.env,
        port=new_settings.server.port,
    )

class _SettingsProxy:
    """
    Proxy для доступа к актуальным настройкам.
    Всегда делегирует к текущему _settings_instance через get_settings().
    Позволяет импортировать settings на уровне модуля и получать актуальные значения.
    """

    @property
    def server(self) -> ServerConfig:
        return get_settings().server

    @property
    def testing(self) -> bool:
        return get_settings().testing

    @property
    def auth(self) -> AuthConfig:
        return get_settings().auth

    @property
    def database(self) -> DatabaseConfig:
        return get_settings().database

    @property
    def llm(self) -> LLMConfig:
        return get_settings().llm

    @property
    def llm_context(self) -> LLMContextConfig:
        return get_settings().llm_context

    @property
    def text_transforms(self) -> TextTransformsConfig:
        return get_settings().text_transforms

    @property
    def provider_litserve(self) -> ProviderLitserveConfig:
        return get_settings().provider_litserve

    @property
    def worker(self) -> WorkerConfig:
        return get_settings().worker

    @property
    def logging(self) -> LoggingConfig:
        return get_settings().logging

    @property
    def s3(self) -> S3Config:
        return get_settings().s3

    @property
    def voice(self) -> SpeechProvidersConfig:
        return get_settings().voice

    @property
    def telegram(self) -> TelegramConfig:
        return get_settings().telegram

    @property
    def whatsapp(self) -> WhatsAppConfig:
        return get_settings().whatsapp

    @property
    def nano_banana(self) -> NanoBananaConfig:
        return get_settings().nano_banana

    @property
    def proxy(self) -> ProxyConfig:
        return get_settings().proxy

    @property
    def payment_providers(self) -> PaymentProvidersConfig:
        return get_settings().payment_providers

    @property
    def rag(self) -> RAGConfig:
        return get_settings().rag

    @property
    def sgr(self) -> SGRConfig:
        return get_settings().sgr

    @property
    def legal(self) -> LegalConfig:
        return get_settings().legal

    @property
    def public_site(self) -> PublicSiteConfig:
        return get_settings().public_site

    @property
    def tracing(self) -> TracingConfig:
        return get_settings().tracing

    @property
    def billing(self) -> BillingConfig:
        return get_settings().billing

    @property
    def tasks(self) -> TasksConfig:
        return get_settings().tasks

    @property
    def calendar_sync(self) -> CalendarSyncConfig:
        return get_settings().calendar_sync

    @property
    def push(self) -> PushConfig:
        return get_settings().push

    @property
    def calls(self) -> CallsConfig:
        return get_settings().calls

    @property
    def media_transcriber(self) -> MediaTranscriberConfig:
        return get_settings().media_transcriber

    @property
    def recording_max_duration_seconds(self) -> float:
        return get_settings().recording_max_duration_seconds

    @property
    def transcribe_audio_redis_lock_ttl_seconds(self) -> int:
        return get_settings().transcribe_audio_redis_lock_ttl_seconds

    @property
    def ws_presence_heartbeat_interval_seconds(self) -> float:
        return get_settings().ws_presence_heartbeat_interval_seconds

    @property
    def ws_presence_ttl_seconds(self) -> int:
        return get_settings().ws_presence_ttl_seconds

    @property
    def sync_taskiq_wait_result_timeout_seconds(self) -> float:
        return get_settings().sync_taskiq_wait_result_timeout_seconds

    @override
    def __repr__(self) -> str:
        return repr(get_settings())

    @override
    def __str__(self) -> str:
        return str(get_settings())

settings = _SettingsProxy()
