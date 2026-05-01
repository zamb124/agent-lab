"""
Модели конфигурации для различных компонентов системы.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.rag_indexing_schema import IndexProfileConfig


class DemoAuthConfig(BaseModel):
    """
    Демо-вход (логин + пароль) для App Review и тестовых сценариев.
    Выключается через auth.demo.login_enabled: false в conf.json / conf.local.json.
    """

    login_enabled: bool = False
    email: str = "demo@demo.ru"
    company_id: str = "demo"
    subdomain: str = "demo"
    company_name: str = "Demo"
    password: Optional[str] = None


class AuthProviderConfig(BaseModel):
    """Конфигурация провайдера авторизации"""

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scope: str = "openid profile email"
    enabled: bool = True
    token_request_format: str = "form"
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
    demo: DemoAuthConfig = Field(default_factory=DemoAuthConfig)


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
    office_url: Optional[str] = None
    tracing_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL platform_tracing (spans); отдельно от shared",
    )
    redis_url: str = "redis://localhost:8099"


class LoggingConfig(BaseModel):
    """
    Конфигурация логирования платформы.

    Все процессы пишут структурированный JSON (или цветной console в dev) в
    stdout. Файловые хендлеры запрещены: ротация — забота оркестратора
    контейнеров, не приложения.
    """

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "json"
    console_colors: bool = False
    sample_rate_info: float = Field(
        default=1.0,
        description="Доля INFO-записей у hot-path логгеров (sampled_loggers); 1.0 — без сэмплинга",
    )
    sampled_loggers: List[str] = Field(
        default_factory=list,
        description="Префиксы логгеров, к которым применяется sample_rate_info",
    )
    loggers_levels: Dict[str, str] = Field(
        default_factory=dict,
        description="Точные уровни для конкретных логгеров: {'sqlalchemy.engine': 'WARNING'}",
    )
    drop_keys: List[str] = Field(
        default_factory=list,
        description="Ключи лог-записи, значение которых заменяется на REDACT_PLACEHOLDER",
    )
    max_string_len: int = Field(
        default=8192,
        description="Максимальная длина строкового значения; обрезанные помечаются _truncated",
    )
    loki_url: Optional[str] = Field(
        default=None,
        description=(
            "URL Loki push API для отправки логов с хоста (dev-режим). "
            "Пример: http://localhost:3100/loki/api/v1/push. "
            "Если None — логи идут только в stdout (Docker Alloy подхватит)."
        ),
    )
    loki_enabled: bool = Field(
        default=False,
        description=(
            "Включить прямую отправку логов в Loki (используется в dev, "
            "когда сервисы запускаются на хосте вне Docker). "
            "В prod/test логи собирает Alloy из stdout контейнеров."
        ),
    )
    loki_query_url: Optional[str] = Field(
        default=None,
        description=(
            "URL Loki query API для поиска логов из приложения (GET /loki/api/v1/query_range). "
            "Пример: http://localhost:3100 или http://loki:3100. "
            "Если None, а задан loki_url (push), базовый URL берётся как scheme://netloc от loki_url. "
            "Если оба пусты — API логов возвращает 503. "
            "Используется flows logs API и admin logs API."
        ),
    )
    grafana_public_url: Optional[str] = Field(
        default=None,
        description=(
            "Публичный origin Grafana без завершающего слэша (ссылки Explore для company_id system). "
            "Пример: https://grafana.humanitec.ru."
        ),
    )
    grafana_loki_datasource_uid: Optional[str] = Field(
        default=None,
        description=(
            "UID источника Loki в Grafana (Provisioning). Совместно с grafana_public_url даёт logs_explore_url в ошибках для system."
        ),
    )
    grafana_org_id: str = Field(
        default="1",
        description="orgId в URL Grafana Explore для deep-link.",
    )

    def resolve_loki_query_http_base(self) -> Optional[str]:
        """
        Базовый URL хоста Loki для LokiClient (GET /loki/api/v1/query_range).

        Приоритет: loki_query_url; иначе scheme://netloc из loki_url (например push …/loki/api/v1/push).
        """
        if self.loki_query_url:
            base = self.loki_query_url.strip()
            return base.rstrip("/") if base else None
        if not self.loki_url:
            return None
        parsed = urlparse(self.loki_url.strip())
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


class ServerConfig(BaseModel):
    """Конфигурация сервера"""

    name: str = "core"
    env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    deployment_version: Optional[str] = Field(
        default=None,
        description="Уникальная метка релиза для /health и сброса PWA-кэша в браузере; в проде задавать на каждый выкат (ENV SERVER__DEPLOYMENT_VERSION или server.deployment_version в JSON).",
    )

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
    office_service_url: Optional[str] = None
    provider_litserve_service_url: Optional[str] = None
    browser_service_url: Optional[str] = None
    voice_service_url: Optional[str] = None
    platform_public_base_url: Optional[str] = Field(
        default="https://humanitec.ru",
        description="Публичный origin без завершающего слэша для deep link (календарь, Sync join).",
    )
    document_server_dev_upstream_url: Optional[str] = Field(
        default=None,
        description=(
            "development/test: реальный HTTP origin Document Server для DevInterServiceProxy "
            "(/web-apps, /common, /cache, /fonts, /sdkjs). Публичный origin в editor-config — "
            "office.document_server_public_url (тот же host, что shell, например :8002)."
        ),
    )

    # Порты по умолчанию для каждого сервиса
    _default_ports: Dict[str, int] = {
        "flows": 8001,
        "frontend": 8002,
        "crm": 8003,
        "rag": 8004,
        "sync": 8005,
        "scheduler": 8006,
        "office": 8008,
        "browser": 8009,
        "provider_litserve": 8014,
        "voice": 8015,
    }

    def get_service_url(self, service: Optional[str] = None) -> str:
        """
        Возвращает URL сервиса.

        Args:
            service: Имя сервиса (flows, crm, office, …). Если None — URL текущего сервиса.
        """
        if service is None:
            return f"http://localhost:{self.port}"

        url_attr = f"{service}_service_url"
        url = getattr(self, url_attr, None)
        if url:
            return url

        default_port = self._default_ports.get(service, 8001)
        if service == "provider_litserve":
            return f"http://127.0.0.1:{default_port}"
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
    mock_transcript_text: str = "Тестовая транскрипция"
    cloud_ru: CloudRuSTTConfig = Field(default_factory=CloudRuSTTConfig)


class TelegramConfig(BaseModel):
    """Конфигурация Telegram ботов"""

    enabled: bool = True
    api_base: str = "https://api.telegram.org"
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


class PaymentProviderConfigEntry(BaseModel):
    """Конфигурация одного платежного провайдера (для env-override через Pydantic)"""
    model_config = ConfigDict(extra="allow")

    provider_type: str = "yoomoney"
    enabled: bool = True
    account_number: Optional[str] = None
    notification_secret: Optional[str] = None
    quickpay_url: str = "https://yoomoney.ru/quickpay/confirm.xml"
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class PaymentProvidersConfig(BaseModel):
    """Конфигурация платежных провайдеров"""

    default_provider: Optional[str] = None
    sync_enabled: bool = Field(default=False, description="Включена ли периодическая сверка транзакций")
    sync_cron: str = Field(default="*/30 * * * *", description="Cron-расписание для сверки транзакций")
    providers: Dict[str, PaymentProviderConfigEntry] = Field(
        default_factory=dict, description="Платежные провайдеры (yoomoney_main, yukassa_main, etc.)"
    )


class EmbeddingApiConfig(BaseModel):
    """Эмбеддинг: ``model``, ``dimension``, ``base_url`` в форме OpenAI/OpenRouter (единый блок для всех провайдеров)."""

    model_config = ConfigDict(extra="forbid")

    model: str = "baai/bge-m3"
    dimension: int = 1024
    # Явный override корня ``…/v1``; пусто при ``provider=openrouter`` — из ``llm.<active>.base_url``.
    base_url: Optional[str] = None


class EmbeddingConfig(BaseModel):
    """Конфигурация embedding: ``provider`` и вложенный блок ``api`` (``model``, ``dimension``, опционально ``base_url``)."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openrouter", "provider_litserve"] = "openrouter"
    api: EmbeddingApiConfig = Field(default_factory=EmbeddingApiConfig)

    @model_validator(mode="before")
    @classmethod
    def _lift_flat_api_fields_into_api(cls, data: Any) -> Any:
        """Плоские ``model`` / ``dimension`` / ``base_url`` на уровне ``embedding`` -> ``api`` (обратная совместимость с merge JSON)."""
        if not isinstance(data, dict):
            return data
        api: Dict[str, Any] = dict(data.get("api") or {})
        for k in ("model", "dimension", "base_url"):
            if k in data:
                api[k] = data.pop(k)
        data["api"] = api
        return data


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

    # Legacy: override ключа эмбеддингов pgvector (ENV); иначе llm.<provider>.api_key. У agentset — см. AgentsetRAGProvider.
    embedding_api_key: Optional[str] = None
    # Средняя цена за 1M токенов (в рублях). ~$0.05 ≈ 5₽
    embedding_cost_per_1m_tokens: float = 5.0
    # Наценка платформы на embedding (1.1 = +10%)
    embedding_platform_markup: float = 1.1

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 100

    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RerankerApiRuntimeConfig(BaseModel):
    """
    HTTP-реранкер: таймаут и опционально полный URL эндпоинта (override).

    При ``provider=provider_litserve`` URL по умолчанию строится из ``provider_litserve.api.base_url`` + ``/rerank``.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: Optional[str] = None
    timeout_seconds: float = 60.0


class RerankerRuntimeConfig(BaseModel):
    """Реранкер: ``provider`` + ``api``."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["none", "provider_litserve"] = "none"
    api: Optional[RerankerApiRuntimeConfig] = None
    # Биллинг (как у embedding в pgvector): оценка по tiktoken, запись через BillingService
    cost_per_1m_tokens: float = 5.0
    platform_markup: float = 1.1
    billing_model_id: str = "rerank"

    @model_validator(mode="before")
    @classmethod
    def _merge_reranker_api(cls, data: Any) -> Any:
        """Плоские ``base_url`` / ``timeout_seconds`` и вложенный ``api``."""
        if not isinstance(data, dict):
            return data
        api: Dict[str, Any] = {}
        if isinstance(data.get("api"), dict):
            api.update(data["api"])
        flat_base = data.pop("base_url", None)
        flat_timeout = data.pop("timeout_seconds", None)
        if flat_base is not None:
            api["base_url"] = flat_base
        if flat_timeout is not None:
            api["timeout_seconds"] = float(flat_timeout)
        if api:
            data["api"] = api
        return data

    @model_validator(mode="after")
    def _ensure_api_object_for_provider_litserve(self) -> "RerankerRuntimeConfig":
        if self.provider == "provider_litserve" and self.api is None:
            object.__setattr__(self, "api", RerankerApiRuntimeConfig())
        return self

    @property
    def base_url(self) -> Optional[str]:
        if self.provider != "provider_litserve" or self.api is None:
            return None
        u = self.api.base_url
        if u is None or not str(u).strip():
            return None
        return str(u).strip()

    @property
    def timeout_seconds(self) -> float:
        if self.provider == "provider_litserve" and self.api is not None:
            return float(self.api.timeout_seconds)
        return 60.0


class ProviderLitserveApiConfig(BaseModel):
    """OpenAI-совместимый корень (как ``llm.openrouter.base_url``): ``…/v1`` для embeddings, rerank, models."""

    model_config = ConfigDict(extra="forbid")

    base_url: Optional[str] = None


class ProviderLitserveInfraConfig(BaseModel):
    """
    Деплой локального OpenAI-совместимого LitServe: один HTTP-порт, воркеры эмбеддингов и реранка.

    Относится к процессу ``apps.provider_litserve.main``, не к доменному ``rag.reranker``.
    Переопределение деплоя: ``services.provider_litserve``; ENV: ``PROVIDER_LITSERVE__INFRA__*``.
    """

    model_config = ConfigDict(extra="forbid")

    backend: Literal["placeholder", "flagllm"] = "placeholder"
    host: str = "0.0.0.0"
    gateway_port: int = 8014
    accelerator: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    workers_per_device: int = 1
    request_timeout_seconds: float = 300.0
    fast_queue: bool = False

    max_passages: int = 128
    max_query_chars: int = 16384
    max_passage_chars: int = 64000
    max_length: int = 1024
    model_batch_size: int = 8
    model_id: str = "BAAI/bge-reranker-v2-gemma"

    use_fp16: bool = True
    use_bf16: bool = False
    normalize_scores: bool = True

    embedding_model_id: str = "BAAI/bge-m3"
    embedding_openai_model_id: str = "baai/bge-m3"
    rerank_openai_model_id: str = "baai/bge-reranker-v2-gemma"
    llm_model_id: str = "Qwen/Qwen2.5-1.5B-Instruct"
    embedding_model_ids: list[str] = Field(default_factory=list)
    rerank_model_ids: list[str] = Field(default_factory=list)
    llm_model_ids: list[str] = Field(default_factory=list)
    hf_token: str | None = None
    sqlite_path: str = "./data/provider_litserve/registry.db"


class ProviderLitserveConfig(BaseModel):
    """Локальные модели эмбеддинга/реранка: клиентский корень API (``api``) и инфраструктура LitServe (``infra``)."""

    model_config = ConfigDict(extra="forbid")

    api: ProviderLitserveApiConfig = Field(default_factory=ProviderLitserveApiConfig)
    infra: ProviderLitserveInfraConfig = Field(default_factory=ProviderLitserveInfraConfig)

    def resolve_openai_v1_base_url(self) -> str:
        raw = self.api.base_url
        if raw is None or not str(raw).strip():
            raise ValueError("provider_litserve.api.base_url пуст")
        return normalize_openai_v1_base_url(str(raw).strip())


class RagTtlConfig(BaseModel):
    """
    TTL по умолчанию и параметры фоновой очистки просроченных документов RAG.

    Клиент задаёт время жизни через ``ttl_seconds`` в metadata при загрузке;
    ``0`` — бессрочно. Если ключ отсутствует, применяется ``default_ttl_seconds``.
    Джоба планируется процессом ``scheduler``, исполняется в очереди ``rag``.
    """

    model_config = ConfigDict(extra="forbid")

    cleanup_enabled: bool = True
    default_ttl_seconds: int = Field(
        default=864000,
        ge=1,
        description="Интервал в секундах при отсутствии ttl_seconds в metadata (864000 с = 10 суток).",
    )
    cleanup_cron: str = Field(
        default="0 * * * *",
        description="Cron (UTC) для тика удаления просроченных документов.",
    )
    cleanup_batch_size: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Максимум документов за один проход удаления.",
    )


class RAGConfig(BaseModel):
    """Конфигурация RAG системы"""

    enabled: bool = False
    default_provider: str = "agentset"

    # Общая конфигурация embeddings для всех провайдеров
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    providers: Dict[str, RAGProviderConfig] = Field(default_factory=dict)
    reranker: RerankerRuntimeConfig = Field(default_factory=RerankerRuntimeConfig)
    document_indexing: IndexProfileConfig = Field(
        default_factory=IndexProfileConfig,
        description="Парсинг, нарезка, lexical/search_defaults для индексации и поиска (без БД-профилей).",
    )
    ttl: RagTtlConfig = Field(
        default_factory=RagTtlConfig,
        description="TTL индексируемых документов и периодическая очистка.",
    )

    def get_enabled_provider_key(self, override: Optional[str] = None) -> str:
        """Имя провайдера из ``override`` или ``default_provider`` с проверкой ``rag.enabled`` и ``providers[name].enabled``."""
        if not self.enabled:
            raise ValueError("RAG не включен в конфигурации (rag.enabled = false)")
        key = (override if override is not None else self.default_provider).strip()
        if not key:
            raise ValueError("rag.default_provider пуст")
        if key not in self.providers:
            available = ", ".join(sorted(self.providers.keys()))
            raise ValueError(f"Неизвестный RAG провайдер: {key}. Доступные: {available}")
        pcfg = self.providers[key]
        if not pcfg.enabled:
            raise ValueError(f"Провайдер {key} отключен (enabled = false)")
        return key


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
    tempo_http_url: str = Field(
        default="http://localhost:3200",
        description=(
            "URL HTTP API Grafana Tempo для чтения трейсов (GET /api/traces/{id}, GET /api/search). "
            "Порт 3200 — стандартный для Tempo HTTP. "
            "Пример prod: http://tempo:3200. "
            "Используется flows traces API и admin tracing API при чтении из Tempo."
        ),
    )
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

    provider: str = Field(default="openai", description="Провайдер: openai, openrouter, bothub, provider_litserve")
    default_model: str = Field(default="gpt-4o")
    vision_model: str = Field(
        default="gemini-2.5-pro-preview", description="Модель для multimodal/vision запросов"
    )
    temperature: float = Field(default=0.2)
    max_tokens: Optional[int] = Field(default=None)
    timeout: float = Field(default=300.0)
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


class SpeechToChatConfig(BaseModel):
    """Серверный egress «речь в ленту»: сегменты LiveKit и опрос TaskIQ в sync worker."""

    segment_seconds: int = Field(
        default=60,
        ge=1,
        description="Длительность одного сегмента segmented egress (сек). Дольше — реже сообщения в ленту.",
    )
    speech_segment_discard_below_max_volume_db: float = Field(
        default=-45.0,
        description="Если volumedetect max_volume (dB) строго меньше порога, сегмент не публикуется в канал.",
    )
    speech_segment_trim_silence_threshold_db: float = Field(
        default=-50.0,
        description="Порог silenceremove (dB) при обрезке тишины с начала и конца сегмента.",
    )
    speech_segment_trim_min_silence_sec: float = Field(
        default=0.35,
        ge=0.05,
        description="Минимальная длительность участка тишины (сек), чтобы silenceremove считал её границей.",
    )
    speech_segment_min_post_duration_ms: int = Field(
        default=200,
        ge=0,
        description="После volumedetect/trim не публиковать сегмент короче (мс).",
    )
    poll_initial_delay_seconds: float = Field(default=4.0, ge=0)
    poll_interval_seconds: float = Field(default=4.0, ge=0)
    poll_lock_ttl_seconds: int = Field(
        default=900,
        ge=60,
        description="TTL Redis single-flight ключа sync:stc_poll:{company}:{call_id}; внутри тика периодически продлевается.",
    )
    poll_lock_refresh_interval_seconds: float = Field(
        default=60.0,
        ge=5.0,
        description="Интервал EXPIRE для того же ключа, пока тик держит lock.",
    )
    poll_lock_busy_retry_seconds: float = Field(
        default=8.0,
        ge=0.5,
        description="Задержка перед следующим kiq, если lock занят другим воркером.",
    )
    max_segments_per_poll_per_track: int = Field(
        default=1,
        ge=1,
        le=128,
        description="Сколько новых сегментов (сообщений) максимум выложить за один тик опроса на один микрофонный трек.",
    )
    livekit_client_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        description="Таймаут aiohttp для Twirp LiveKit в тике poll и при stop_speech_egresses.",
    )
    segment_http_download_timeout_seconds: float = Field(
        default=120.0,
        ge=10.0,
        description="Таймаут httpx при скачивании байт сегмента по URL (не S3 SDK).",
    )
    s3_segment_list_page_size: int = Field(
        default=128,
        ge=1,
        le=1000,
        description="Размер страницы list_objects_v2 по префиксу сегментов в S3.",
    )

    @model_validator(mode="after")
    def _poll_lock_refresh_before_ttl(self) -> SpeechToChatConfig:
        if self.poll_lock_refresh_interval_seconds >= self.poll_lock_ttl_seconds:
            raise ValueError(
                "poll_lock_refresh_interval_seconds должен быть меньше poll_lock_ttl_seconds"
            )
        return self


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
    speech_to_chat: SpeechToChatConfig = Field(default_factory=SpeechToChatConfig)
    finalize_recording_egress_poll_interval_seconds: float = Field(
        default=3.0,
        ge=0.5,
        description="Интервал asyncio.sleep между опросами list_egress при finalize записи звонка.",
    )
    finalize_recording_egress_wait_timeout_seconds: float = Field(
        default=600.0,
        ge=30.0,
        description="Сколько секунд ждать появления location у composite egress при finalize записи (не STT).",
    )


class PushConfig(BaseModel):
    """Web Push (VAPID), APNs и FCM.

    Для APNs пустые apns_team_id / apns_key_id / apns_private_key дополняются из
    auth.providers.apple при том же .p8 (ключ в Apple должен иметь capability APNs).

    Для FCM используется Firebase Admin HTTP v1 API с service account JSON. Содержимое
    google-services service account кладётся в fcm_credentials_json (одной строкой
    JSON или объектом из conf.json). Не путать с google-services.json в Android-сборке —
    это разные файлы: первый serverside (приватный ключ сервиса), второй clientside
    (Sender ID и project number, кладётся в mobile/android/app/).
    """

    enabled: bool = False
    vapid_public_key: Optional[str] = None
    vapid_private_key: Optional[str] = None
    vapid_email: str = "admin@humanitec.ru"
    apns_team_id: Optional[str] = None
    apns_key_id: Optional[str] = None
    apns_private_key: Optional[str] = None
    apns_bundle_id: Optional[str] = None
    apns_use_sandbox: bool = False
    fcm_credentials_json: Optional[Any] = None
    fcm_project_id: Optional[str] = None


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


def default_billing_resource_base_prices() -> Dict[str, Dict[str, float]]:
    """
    Базовый каталог цен до merge с shared storage и пер-компанией.

    Каждое значение — цена в условных рублях за одну единицу списания (что именно считается
    единицей, задаёт правило settlement: токены LLM, один вызов livekit и т.д.).
    Итоговая цена = значение × множитель тарифа компании (см. DEFAULT_TARIFF_PRICES).

    Ключи верхнего уровня — категория первого сегмента resource_name (формат category:resource).
    Внутри категории: имя ресурса или "*" для цены по умолчанию.

    - llm: модели (трейсы llm.*, flows.llm_resource.*, flows.llm.*). "*" — типично руб/токен.
    - embedding: RAG эмбеддинги (rag.embed.*).
    - billing:rub — единица = 1 ₽; quantity из platform.billing.settlement_quantity_rub (OpenRouter USD×usd_to_rub_rate).
    - livekit: поминутное списание — room_minute, egress_composite_minute, egress_segmented_minute
      (см. core/calls/livekit_usage_spans.py); legacy-ключи room_create, egress_composite, egress_segmented
      сохранены с теми же числами для обратной совместимости прайса; "*" — прочие livekit:*.

    Категория tool в биллинге не используется (тулы flows бесплатны в учёте).
    Подробнее: conf.json → billing._docs_ru, configuration.mdc, billing.mdc.
    """
    return {
        "llm": {"*": 0.0001},
        "embedding": {"*": 0.00005},
        "billing": {"rub": 1.0},
        "voice": {"session_minute": 0.01, "*": 0.0},
        "livekit": {
            "room_minute": 0.01,
            "egress_composite_minute": 0.05,
            "egress_segmented_minute": 0.02,
            "room_create": 0.01,
            "egress_composite": 0.05,
            "egress_segmented": 0.02,
            "*": 0.0,
        },
    }


class BillingSpanSettlementConfig(BaseModel):
    """Фоновое списание по spans с platform.billing.pending_settlement (idle worker)."""

    enabled: bool = Field(
        default=False,
        description="Включить тик settlement на idle worker (создание usage из spans).",
    )
    cron: str = Field(
        default="*/15 * * * *",
        description="Cron выражение расписания тика span settlement.",
    )
    lookback_minutes: int = Field(
        default=360,
        ge=1,
        description="За сколько минут назад искать необработанные spans (окно после простоя воркера).",
    )
    batch_limit: int = Field(
        default=500,
        ge=1,
        description="Максимум spans, обрабатываемых за один тик.",
    )
    fallback_user_id: str = Field(
        default="",
        description="user_id для UsageRecord, если в span нет user_id (пусто — span пропускается, ошибка в логе).",
    )


class BillingConfig(BaseModel):
    """Тарификация: базовые цены из конфига + override через API system; settlement по трейсам."""

    balance_enforcement_enabled: bool = Field(
        default=True,
        description="Pre-flight: блокировать старт операций с pending_settlement при balance <= 0.",
    )
    balance_enforcement_exempt_company_ids: List[str] = Field(
        default_factory=lambda: ["system"],
        description="company_id без проверки баланса (например system и демо для локальной разработки).",
    )
    resource_base_prices: Dict[str, Dict[str, float]] = Field(
        default_factory=default_billing_resource_base_prices,
        description="Дерево category → resource → цена в руб./единицу списания; merge с storage override.",
    )
    usd_to_rub_rate: float = Field(
        default=85.0,
        gt=0.0,
        description=(
            "Fallback-курс USD/RUB. При старте сервиса платформа получает актуальный курс"
            " от ЦБ РФ (cbr.ru/scripts/XML_daily.asp) и обновляет его каждые 5 минут."
            " Это значение используется только если ЦБ временно недоступен или до первого"
            " успешного ответа. Влияет на platform.billing.settlement_quantity_rub"
            " в spans OpenRouter (round(provider_reported_cost_usd × rate))."
        ),
    )
    span_settlement: BillingSpanSettlementConfig = Field(
        default_factory=BillingSpanSettlementConfig,
        description="Параметры фоновой джобы преобразования spans в usage.",
    )


class VoiceSTTSettings(BaseModel):
    """Настройки STT-провайдера voice сервиса."""

    provider: str = "cloud_ru"
    mock_text: str = "Тестовая транскрипция"


class VoiceTTSSettings(BaseModel):
    """Настройки TTS-провайдера voice сервиса."""

    provider: str = "kokoro"
    kokoro_sample_rate: int = 24000
    kokoro_accelerator: str = "cpu"
    chunk_max_chars: int = 100
    lookahead_tokens: int = 20


class VoiceVADSettings(BaseModel):
    """Настройки VAD-провайдера voice сервиса."""

    model: str = "silero"
    sample_rate: int = 16000
    threshold: float = 0.5
    min_speech_ms: int = 300
    min_silence_ms: int = 500
    echo_compensation: float = 0.2


class VoiceBargeInSettings(BaseModel):
    """Настройки механизма прерывания (barge-in)."""

    enabled: bool = True
    smart_turn_buffer_ms: int = 500
    smart_turn_command_words: list[str] = Field(
        default_factory=lambda: ["стоп", "хватит", "подожди", "стой"]
    )
    flush_timeout_ms: int = 200
    cooldown_ms: int = 300


class VoiceQueueSettings(BaseModel):
    """Настройки размеров внутренних очередей голосовой сессии."""

    audio_in_size: int = 1024
    audio_out_size: int = 256
    text_size: int = 256
    synthesis_size: int = 64


class YouTubeConfig(BaseModel):
    """Конфигурация скачивания аудио с YouTube через yt-dlp."""

    max_duration_seconds: int = Field(
        default=7200,
        ge=60,
        description="Максимальная длительность видео для скачивания (сек).",
    )
    preferred_codec: str = Field(
        default="mp3",
        description="Кодек для извлечения аудио (mp3, aac, wav).",
    )
    preferred_quality: str = Field(
        default="64",
        description="Качество аудио (kbps).",
    )
    socket_timeout: int = Field(
        default=30,
        ge=5,
        description="Таймаут сетевых операций yt-dlp (сек).",
    )


class MediaTranscriberConfig(BaseModel):
    """Конфигурация единого медиа-пайплайна транскрипции."""

    max_file_size_bytes: int = Field(
        default=500 * 1024 * 1024,
        ge=1024,
        description="Максимальный размер файла для транскрипции (байт).",
    )
    default_language: Optional[str] = Field(
        default=None,
        description="Язык по умолчанию для STT (None — из STT конфигурации).",
    )
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
