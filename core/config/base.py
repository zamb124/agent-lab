"""
Базовая конфигурация приложения.
"""

from typing import ClassVar, override

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import PydanticBaseSettingsSource, SettingsConfigDict

from core.config.loader import load_merged_config
from core.config.models import (
    AuthConfig,
    BillingConfig,
    CalendarSyncConfig,
    CallsConfig,
    CodeRunnerSettings,
    CustomerAuthConfig,
    DatabaseConfig,
    EventsConfig,
    FilesConfig,
    GeocodingConfig,
    GoogleWorkspaceConfig,
    GuestRuntimeFarmConfig,
    LanesConfig,
    LegalConfig,
    LLMConfig,
    LoggingConfig,
    MailConfig,
    MailSyncConfig,
    MCPBrandingConfig,
    MCPCatalogConfig,
    MediaTranscriberConfig,
    NanoBananaConfig,
    OpenFGAConfig,
    PaymentProvidersConfig,
    PlatformBrandConfig,
    ProviderLitserveConfig,
    ProxyConfig,
    PublicSiteConfig,
    PushConfig,
    RAGConfig,
    RealtimeConfig,
    S3Config,
    SecretsConfig,
    ServerConfig,
    SGRConfig,
    SpeechProvidersConfig,
    TasksConfig,
    TelegramConfig,
    TextTransformsConfig,
    TracingConfig,
    WorkerConfig,
    default_platform_brands,
)
from core.llm_context.models import LLMContextConfig
from core.logging import get_logger
from core.types import JsonObject, JsonValue

logger = get_logger(__name__)

PLATFORM_DEFAULT_APEX = "linnex.io"
"""Deployment default apex. Single source for identities that must stay stable
across brands; host-aware code uses resolve_brand()."""


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
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)
    guest_runtime: GuestRuntimeFarmConfig = Field(default_factory=GuestRuntimeFarmConfig)
    mcp_branding: MCPBrandingConfig = Field(default_factory=MCPBrandingConfig)
    mcp_catalog: MCPCatalogConfig = Field(default_factory=MCPCatalogConfig)
    voice: SpeechProvidersConfig = Field(default_factory=SpeechProvidersConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    nano_banana: NanoBananaConfig = Field(default_factory=NanoBananaConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    payment_providers: PaymentProvidersConfig = Field(default_factory=PaymentProvidersConfig)
    customer_auth: CustomerAuthConfig = Field(default_factory=CustomerAuthConfig)
    geocoding: GeocodingConfig = Field(default_factory=GeocodingConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    sgr: SGRConfig = Field(default_factory=SGRConfig)
    legal: LegalConfig = Field(default_factory=LegalConfig)
    public_site: PublicSiteConfig = Field(default_factory=PublicSiteConfig)
    primary_platform_domain: str = Field(
        default=PLATFORM_DEFAULT_APEX,
        description="Deployment default apex when Host is unavailable (TURN, VAPID). Host-aware code uses resolve_brand().",
    )
    platform_brands: dict[str, PlatformBrandConfig] = Field(
        default_factory=default_platform_brands,
        description="Бренды платформы по registrable apex-домену.",
    )
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    billing: BillingConfig = Field(default_factory=BillingConfig)
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    realtime: RealtimeConfig = Field(default_factory=RealtimeConfig)
    lanes: LanesConfig = Field(default_factory=LanesConfig)
    openfga: OpenFGAConfig = Field(default_factory=OpenFGAConfig)
    calendar_sync: CalendarSyncConfig = Field(default_factory=CalendarSyncConfig)
    mail_sync: MailSyncConfig = Field(default_factory=MailSyncConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    google_workspace: GoogleWorkspaceConfig = Field(
        default_factory=GoogleWorkspaceConfig
    )
    push: PushConfig = Field(default_factory=PushConfig)
    calls: CallsConfig = Field(default_factory=CallsConfig)
    media_transcriber: MediaTranscriberConfig = Field(default_factory=MediaTranscriberConfig)
    recording_max_duration_seconds: float = Field(default=3600.0)
    transcribe_audio_redis_lock_ttl_seconds: int = Field(
        default=600,
        ge=60,
        description="TTL Redis SET NX для ключа sync:transcribe_audio:{company_id}:{message_id}.",
    )
    code_runner: CodeRunnerSettings = Field(default_factory=CodeRunnerSettings)
    test_scope_default: str = Field(
        default="",
        description=(
            "Scope MockLLM для запросов без X-Test-Scope в тестовом контуре. "
            "Пусто — scope только из лог-контекста."
        ),
    )

    # extra="forbid": ключ conf.json без поля в Settings — ошибка старта, а не тихо
    # проигнорированная настройка (гейт scripts/gates/repo/conf_keys_declared.py ловит это статически).
    # dotenv_filtering="only_existing": .env разработчика может содержать переменные для
    # других инструментов (ключи деплоя, App Store) — они не проходят через Pydantic.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[".env"],
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="forbid",
        dotenv_filtering="only_existing",
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
    def nano_banana(self) -> NanoBananaConfig:
        return get_settings().nano_banana

    @property
    def proxy(self) -> ProxyConfig:
        return get_settings().proxy

    @property
    def payment_providers(self) -> PaymentProvidersConfig:
        return get_settings().payment_providers

    @property
    def customer_auth(self) -> CustomerAuthConfig:
        return get_settings().customer_auth

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
    def events(self) -> EventsConfig:
        return get_settings().events

    @property
    def realtime(self) -> RealtimeConfig:
        return get_settings().realtime

    @property
    def lanes(self) -> LanesConfig:
        return get_settings().lanes

    @property
    def openfga(self) -> OpenFGAConfig:
        return get_settings().openfga

    @property
    def calendar_sync(self) -> CalendarSyncConfig:
        return get_settings().calendar_sync

    @property
    def mail_sync(self) -> MailSyncConfig:
        return get_settings().mail_sync

    @property
    def mail(self) -> MailConfig:
        return get_settings().mail

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

    @override
    def __repr__(self) -> str:
        return repr(get_settings())

    @override
    def __str__(self) -> str:
        return str(get_settings())

settings = _SettingsProxy()
