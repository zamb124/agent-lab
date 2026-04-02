"""
Модели конфигурации для различных компонентов системы.
"""

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, Field, PrivateAttr


class AuthProviderConfig(BaseModel):
    """Конфигурация провайдера авторизации"""

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scope: str = "openid profile email"
    enabled: bool = True
    apple_team_id: Optional[str] = None
    apple_key_id: Optional[str] = None
    apple_private_key: Optional[str] = None


class AuthConfig(BaseModel):
    """Конфигурация системы авторизации"""

    enabled: bool = True
    permissions_enabled: bool = True
    secret_key: Optional[str] = None
    jwt_secret_key: Optional[str] = None
    session_timeout: int = 3600
    providers: Dict[str, AuthProviderConfig] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    """Конфигурация базы данных: ровно пять URL PostgreSQL + redis (без дублирующего url)."""

    checkpointer_url: str = "postgresql://agent_user:agent_password@localhost:5432/agent_platform"
    shared_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("shared_url", "url"),
    )
    flows_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("flows_url"),
    )
    crm_url: Optional[str] = None
    sync_url: Optional[str] = None
    rag_url: Optional[str] = None
    redis_url: str = "redis://localhost:8099"


class LoggingConfig(BaseModel):
    """Конфигурация логирования"""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    json_format: bool = True
    console_format: str = "structured"
    console_colors: bool = True
    file_enabled: bool = True
    file_path: str = "logs/app.log"
    file_max_bytes: int = 10 * 1024 * 1024
    file_backup_count: int = 5
    console_enabled: bool = True
    app_file_path: str = "logs/app.log"
    worker_file_path: str = "logs/worker.log"
    loggers_levels: Dict[str, str] = Field(default_factory=dict)


class ServerConfig(BaseModel):
    """Конфигурация сервера"""

    name: str = "core"
    env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    deployment_version: Optional[str] = None

    # URL сервисов для межсервисного взаимодействия
    flows_service_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("flows_service_url"),
    )
    crm_service_url: Optional[str] = None
    frontend_service_url: Optional[str] = None
    rag_service_url: Optional[str] = None
    sync_service_url: Optional[str] = None
    scheduler_service_url: Optional[str] = None
    platform_public_base_url: Optional[str] = Field(
        default="https://humanitec.ru",
        description="Публичный origin без завершающего слэша для deep link (календарь, Sync join).",
    )

    # Порты по умолчанию для каждого сервиса
    _default_ports: Dict[str, int] = {
        "flows": 8001,
        "frontend": 8002,
        "crm": 8003,
        "rag": 8004,
        "sync": 8005,
        "scheduler": 8006,
    }

    def get_service_url(self, service: Optional[str] = None) -> str:
        """
        Возвращает URL сервиса.

        Args:
            service: Имя сервиса (flows, crm, frontend, rag). Если None - URL текущего сервиса.
        """
        if service is None:
            return f"http://localhost:{self.port}"

        url_attr = f"{service}_service_url"
        url = getattr(self, url_attr, None)
        if url:
            return url

        default_port = self._default_ports.get(service, 8001)
        return f"http://localhost:{default_port}"

    def get_flows_service_url(self) -> str:
        """URL сервиса flows."""
        return self.get_service_url("flows")

    workers: int = 4
    worker_class: str = "uvicorn.workers.UvicornWorker"
    worker_connections: int = 1000
    max_requests: int = 1000
    max_requests_jitter: int = 50
    timeout: int = 30
    keepalive: int = 2


class WorkerConfig(BaseModel):
    """Конфигурация воркеров"""

    max_workers: int = 4
    task_poll_interval: int = 5

    """Конфигурация FASHN API"""

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: str = "https://api.fashn.ai/v1"
    timeout: int = 120
    poll_interval: float = 5.0
    poll_timeout: int = 600


class CloudRuSTTConfig(BaseModel):
    """Конфигурация cloud.ru STT (Whisper API)."""

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: str = "https://foundation-models.api.cloud.ru/v1/audio/transcriptions"
    model: str = "openai/whisper-large-v3"
    response_format: str = "text"
    temperature: float = 0.5
    language: str = "ru"
    timeout: float = 120.0
    max_upload_bytes: int = 24 * 1024 * 1024
    chunk_duration_seconds: int = 300
    chunk_bitrate_kbps: int = 32
    chunk_sample_rate_hz: int = 16000
    chunk_channels: int = 1


class STTConfig(BaseModel):
    """Конфигурация STT провайдеров."""

    provider: str = "cloud_ru"
    cloud_ru: CloudRuSTTConfig = Field(default_factory=CloudRuSTTConfig)


class TelegramConfig(BaseModel):
    """Конфигурация Telegram ботов"""

    enabled: bool = True
    bots: Dict[str, str] = Field(default_factory=dict)


class WhatsAppConfig(BaseModel):
    """Конфигурация WhatsApp интеграции"""

    enabled: bool = True
    verify_token: Optional[str] = None
    graph_api_version: str = "v18.0"
    graph_api_url: str = "https://graph.facebook.com"


class NanoBananaConfig(BaseModel):
    """Конфигурация Nano Banana (Gemini Image Generation через OpenRouter)"""

    enabled: bool = False
    model_name: str = "google/gemini-2.5-flash-preview-image"
    timeout: int = 60


class AmoCRMConfig(BaseModel):
    """Конфигурация AmoCRM интеграции"""

    access_token: Optional[str] = None


class ProxyConfig(BaseModel):
    """Конфигурация прокси с умной ротацией - проблемные прокси уходят в конец"""

    enabled: bool = False
    proxies: List[str] = Field(
        default_factory=list,
        description="Список прокси URL: ['http://proxy1:8080', 'http://user:pass@proxy2:8080']",
    )
    connect_timeout: float = Field(
        default=4.0,
        description="Таймаут подключения к прокси (секунды)",
    )

    _current_index: int = PrivateAttr(default=0)
    _last_used_proxy: Optional[str] = PrivateAttr(default=None)

    def get_next_proxy(self) -> Optional[str]:
        """Возвращает следующий прокси по round-robin"""
        if not self.enabled or not self.proxies:
            return None

        proxy = self.proxies[self._current_index % len(self.proxies)]
        self._current_index = (self._current_index + 1) % len(self.proxies)
        self._last_used_proxy = proxy
        return proxy

    def mark_last_proxy_failed(self) -> None:
        """
        Перемещает последний использованный прокси в конец списка.
        Следующий запрос пойдёт через другой прокси.
        """
        if not self._last_used_proxy or len(self.proxies) <= 1:
            return

        if self._last_used_proxy in self.proxies:
            self.proxies.remove(self._last_used_proxy)
            self.proxies.append(self._last_used_proxy)
            self._current_index = 0


class PaymentProvidersConfig(BaseModel):
    """Конфигурация платежных провайдеров"""

    default_provider: Optional[str] = None
    providers: Dict[str, Any] = Field(
        default_factory=dict, description="Платежные провайдеры (yoomoney_main, yukassa_main, etc.)"
    )


class EmbeddingConfig(BaseModel):
    """Конфигурация embedding модели."""

    model: str = "baai/bge-m3"
    dimension: int = 1024
    # OpenAI-compatible POST .../embeddings; пусто = OpenRouter (EmbeddingService.OPENROUTER_URL)
    base_url: Optional[str] = None


class RAGProviderConfig(BaseModel):
    """Конфигурация одного RAG провайдера"""

    enabled: bool = False
    api_key: Optional[str] = None  # API ключ провайдера (например Agentset API)
    base_url: Optional[str] = None
    timeout: int = 60

    # Legacy (не используются для pgvector)
    host: Optional[str] = None
    port: Optional[int] = None

    # PgVector specific
    db_url: Optional[str] = None

    # Embeddings - ключ для OpenRouter или другого embedding API
    embedding_api_key: Optional[str] = None
    # Средняя цена за 1M токенов (в рублях). ~$0.05 ≈ 5₽
    embedding_cost_per_1m_tokens: float = 5.0
    # Наценка платформы на embedding (1.1 = +10%)
    embedding_platform_markup: float = 1.1

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 100

    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RAGConfig(BaseModel):
    """Конфигурация RAG системы"""

    enabled: bool = False
    default_provider: str = "agentset"

    # Общая конфигурация embeddings для всех провайдеров
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    providers: Dict[str, RAGProviderConfig] = Field(default_factory=dict)


class SGRConfig(BaseModel):
    """Конфигурация SGR Deep Research сервиса"""

    enabled: bool = False
    base_url: str = "http://localhost:8010"
    api_key: Optional[str] = None
    timeout: float = 300.0
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 8000
    llm_temperature: float = 0.4
    tavily_api_key: Optional[str] = None
    max_steps: int = 6
    max_results: int = 10


class TracingConfig(BaseModel):
    """Конфигурация трейсинга"""

    enabled: bool = True
    service_name: str = "agent-lab"
    postgres_enabled: bool = True
    tempo_enabled: bool = False
    tempo_endpoint: str = "http://localhost:4317"
    sampling_rate: float = 1.0
    retention_days: int = 30


class TasksConfig(BaseModel):
    """Конфигурация TaskIQ"""

    broker_url: str = "redis://localhost:6379/0"
    result_backend_url: Optional[str] = None
    max_workers: int = 4


class CalendarSyncConfig(BaseModel):
    """Конфигурация фоновой синхронизации календаря."""

    enabled: bool = True
    cron: str = "*/1 * * * *"
    lookback_days: int = 7
    lookahead_months: int = 3
    batch_size: int = 100
    max_integrations_per_tick: int = 1000
    max_parallel_integrations: int = 10
    notification_dedup_ttl_seconds: int = 86400
    sync_meeting_reminder_enabled: bool = True
    sync_meeting_reminder_cron: str = "*/1 * * * *"
    sync_meeting_reminder_limit: int = 500


class OpenAIProviderConfig(BaseModel):
    """Конфигурация OpenAI провайдера"""

    api_key: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)


class OpenRouterProviderConfig(BaseModel):
    """Конфигурация OpenRouter провайдера"""

    api_key: Optional[str] = Field(default=None)
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    site_url: str = Field(default="https://platform.local")
    site_name: str = Field(default="platform")


class BothubProviderConfig(BaseModel):
    """Конфигурация Bothub провайдера"""

    api_key: Optional[str] = Field(default=None)
    base_url: str = Field(default="https://bothub.chat/api/v2/openai/v1")


class ModelConfig(BaseModel):
    """Конфигурация модели — переопределение temperature/max_tokens для конкретной модели"""

    temperature: float = Field(default=0.2)
    max_tokens: Optional[int] = Field(default=None)


class LLMConfig(BaseModel):
    """Конфигурация LLM с поддержкой нескольких провайдеров"""

    provider: str = Field(default="openai", description="Провайдер: openai, openrouter, bothub")
    default_model: str = Field(default="gpt-4o")
    vision_model: str = Field(
        default="gemini-2.5-pro-preview", description="Модель для multimodal/vision запросов"
    )
    temperature: float = Field(default=0.2)
    max_tokens: Optional[int] = Field(default=None)
    timeout: float = Field(default=120.0)
    openai: Optional[OpenAIProviderConfig] = Field(default=None)
    openrouter: Optional[OpenRouterProviderConfig] = Field(default=None)
    bothub: Optional[BothubProviderConfig] = Field(default=None)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)


class S3BucketConfig(BaseModel):
    """Конфигурация одного S3 bucket"""

    bucket_name: Optional[str] = Field(
        default=None, description="Реальное имя bucket (если отличается от ключа конфигурации)"
    )
    access_key_id: Optional[str] = Field(default=None)
    secret_access_key: Optional[str] = Field(default=None)
    endpoint_url: Optional[str] = Field(default=None)
    region_name: str = Field(default="us-east-1")
    provider: str = Field(default="aws")
    enabled: bool = Field(default=True)


class S3Config(BaseModel):
    """Конфигурация S3 с поддержкой multiple buckets"""

    enabled: bool = Field(default=False)
    default_bucket: str = Field(default="files")
    buckets: Dict[str, S3BucketConfig] = Field(default_factory=dict)


class CallsConfig(BaseModel):
    """Конфигурация WebRTC звонков: LiveKit SFU и coturn TURN.

    livekit_url       — внутренний Docker URL для сервер-сервер API (ws:// или http://).
    livekit_public_url — публичный URL для браузера (wss:// на продакшене).
                         Если не задан — используется livekit_url.
    """

    livekit_url: str = "ws://localhost:7880"
    livekit_public_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    turn_host: str = ""
    turn_port: int = 3478
    turn_secret: str = ""
    turn_credential_ttl: int = 86400


class PushConfig(BaseModel):
    """Конфигурация Web Push уведомлений"""

    enabled: bool = False
    vapid_public_key: Optional[str] = None
    vapid_private_key: Optional[str] = None
    vapid_email: str = "admin@humanitec.ru"


class LegalConfig(BaseModel):
    """Конфигурация юридической информации компании"""

    company_name_ru: str = "ООО «Энжилабс»"
    company_name_en: str = "Angilabs LLC"
    legal_form_ru: str = "Общество с ограниченной ответственностью"
    legal_form_en: str = "Limited Liability Company"
    inn: Optional[str] = None
    ogrn: Optional[str] = None
    legal_address_ru: Optional[str] = None
    legal_address_en: Optional[str] = None
    contact_email: str = "info@angilabs.ru"
    support_email: str = "support@angilabs.ru"
    dpo_email: str = "dpo@angilabs.ru"
    phone: Optional[str] = None
    min_age: int = 18
    retention_logs: str = "30 дней / 30 days"
    retention_messages: str = "1 год / 1 year"
    retention_accounts: str = "3 года после последней активности / 3 years after last activity"
    cloud_provider: str = "AWS/Yandex Cloud"
    cloud_region: str = "EU/RU"
    analytics_tools: str = "Internal analytics"
    billing_provider: Optional[str] = None
