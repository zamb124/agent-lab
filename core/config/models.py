"""
Модели конфигурации для различных компонентов системы.
"""

from __future__ import annotations

from typing import ClassVar, Literal, Self
from urllib.parse import urlparse

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from core.ai.providers import (
    GITHUB_MODELS_API_VERSION,
    LINNEX_LLM_AUTO_MODEL,
    LINNEX_LLM_PROVIDER,
    LLM_PROVIDER_DEFAULT_BASE_URLS,
    LLM_PROVIDER_DEFAULT_MODELS_URLS,
    LLM_PROVIDER_SMOKE_MODELS,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS,
    AICapability,
    validate_platform_provider_for_capability,
)
from core.models.billing_models import DEFAULT_TARIFF_PRICES
from core.rag_indexing_schema import IndexProfileConfig
from core.types import JsonObject, JsonValue, SpeechProvider, VadProvider
from core.utils.tts_input_steps import TTS_INPUT_STEP_IDS

__all__ = [
    "LINNEX_LLM_AUTO_MODEL",
    "LINNEX_LLM_PROVIDER",
]


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
    password: str | None = None


class AuthProviderConfig(BaseModel):
    """Конфигурация провайдера авторизации"""

    client_id: str | None = None
    client_secret: str | None = None
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scope: str = "openid profile email"
    enabled: bool = True
    token_request_format: str = "form"
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: str | None = None


class AuthConfig(BaseModel):
    """Конфигурация системы авторизации"""

    enabled: bool = Field(
        default=True,
        description=(
            "Включает обязательную авторизацию. Отключение auth.enabled само по себе "
            "не создаёт пользователя; локальный dev auto-context включается отдельным флагом."
        ),
    )
    dev_auto_context_enabled: bool = Field(
        default=False,
        description=(
            "Только для локальной разработки: при auth.enabled=false в non-production "
            "создаёт dev-пользователя для защищённых маршрутов. В testing игнорируется."
        ),
    )
    dev_auto_user_id: str = "dev-auto-user"
    dev_auto_company_id: str = "system"
    dev_auto_company_name: str = "System"
    dev_auto_groups: list[str] = Field(default_factory=lambda: ["admin", "developers"])
    secret_key: str | None = None
    jwt_secret_key: str | None = None
    session_timeout: int = 3600
    providers: dict[str, AuthProviderConfig] = Field(default_factory=dict)
    demo: DemoAuthConfig = Field(default_factory=DemoAuthConfig)


class DatabaseConfig(BaseModel):
    """Конфигурация базы данных: ровно пять URL PostgreSQL + redis (без дублирующего url)."""

    checkpointer_url: str = "postgresql://agent_user:agent_password@localhost:5432/agent_platform"
    shared_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("shared_url", "url"),
    )
    flows_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("flows_url"),
    )
    crm_url: str | None = None
    sync_url: str | None = None
    rag_url: str | None = None
    office_url: str | None = None
    worktracker_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_worktracker (ядро задач WorkItem)",
    )
    secrets_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_secrets (версионируемые переменные и секреты)",
    )
    tracing_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_tracing (spans); отдельно от shared",
    )
    search_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_search (search_indexes, crawl state)",
    )
    wiki_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_wiki (страницы базы знаний, ревизии, ссылки)",
    )
    realtime_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_realtime (durable-лог PlatformEvent)",
    )
    stock_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_stock (леджер склада: moves, quants, valuation)",
    )
    shop_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_shop (витрины, каталог, заказы, домены)",
    )
    geo_url: str | None = Field(
        default=None,
        description="PostgreSQL platform_geo (адресный справочник, дорожный граф, PostGIS)",
    )
    redis_url: str = "redis://localhost:8099"
    redis_inventory_interval_seconds: int = Field(
        default=900,
        description="Интервал idle-задачи redis_inventory_tick (секунды).",
        ge=60,
    )
    statement_timeout_ms: int = Field(
        default=30_000,
        description=(
            "PostgreSQL statement_timeout по умолчанию (мс). 0 — без ограничения."
        ),
        ge=0,
    )
    lock_timeout_ms: int = Field(
        default=10_000,
        description="PostgreSQL lock_timeout (мс). 0 — без ограничения.",
        ge=0,
    )
    idle_in_transaction_session_timeout_ms: int = Field(
        default=60_000,
        description=(
            "PostgreSQL idle_in_transaction_session_timeout (мс). 0 — без ограничения. "
            "Защищает от висящих транзакций, удерживающих локи."
        ),
        ge=0,
    )
    pool_max_connections: int = Field(
        default=5,
        description="Верхняя граница пула Oxyde на одну базу процесса.",
        ge=1,
    )
    pool_acquire_timeout_seconds: float = Field(
        default=30,
        description="Сколько секунд ждать свободное соединение пула Oxyde.",
        gt=0,
    )


class SecretsConfig(BaseModel):
    """Конфигурация микросервиса secrets.

    ``encryption_key`` — отдельный от ``auth.jwt_secret_key`` ключ шифрования значений
    секретных переменных. Zero-Guess: при попытке зашифровать без ключа сервис падает.
    """

    encryption_key: str | None = Field(
        default=None,
        description="Ключ шифрования значений секретных переменных (ENV SECRETS__ENCRYPTION_KEY)",
    )


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
    sampled_loggers: list[str] = Field(
        default_factory=list,
        description="Префиксы логгеров, к которым применяется sample_rate_info",
    )
    loggers_levels: dict[str, str] = Field(
        default_factory=dict,
        description="Точные уровни для конкретных логгеров: {'sqlalchemy.engine': 'WARNING'}",
    )
    drop_keys: list[str] = Field(
        default_factory=list,
        description="Ключи лог-записи, значение которых заменяется на REDACT_PLACEHOLDER",
    )
    max_string_len: int = Field(
        default=8192,
        description="Максимальная длина строкового значения; обрезанные помечаются _truncated",
    )
    loki_url: str | None = Field(
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
    loki_query_url: str | None = Field(
        default=None,
        description=(
            "URL Loki query API для поиска логов из приложения (GET /loki/api/v1/query_range). "
            "Пример: http://localhost:3100 или http://loki:3100. "
            "Если None, а задан loki_url (push), базовый URL берётся как scheme://netloc от loki_url. "
            "Если оба пусты — API логов возвращает 503. "
            "Используется flows logs API и admin logs API."
        ),
    )
    grafana_public_url: str | None = Field(
        default=None,
        description=(
            "Публичный origin Grafana без завершающего слэша (ссылки Explore для company_id system). "
            "Пример: https://grafana.linnex.io."
        ),
    )
    grafana_loki_datasource_uid: str | None = Field(
        default=None,
        description=(
            "UID источника Loki в Grafana (Provisioning). Совместно с grafana_public_url даёт logs_explore_url в ошибках для system."
        ),
    )
    grafana_org_id: str = Field(
        default="1",
        description="orgId в URL Grafana Explore для deep-link.",
    )

    def resolve_loki_query_http_base(self) -> str | None:
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
    granian_workers: int = Field(
        default=1,
        ge=1,
        description=(
            "Число процессов Granian для python -m apps.<svc>.main. "
            "Больше одного — отдельные event loop. CLI в k8s задаёт GRANIAN_WORKERS сам."
        ),
    )
    granian_runtime_threads: int = Field(
        default=2,
        ge=1,
        description="Потоки runtime Granian для python -m. CLI в k8s задаёт GRANIAN_RUNTIME_THREADS сам.",
    )
    deployment_version: str | None = Field(
        default=None,
        description="Уникальная метка релиза для /health и сброса PWA-кэша в браузере; в проде задавать на каждый выкат (ENV SERVER__DEPLOYMENT_VERSION или server.deployment_version в JSON).",
    )

    # URL сервисов для межсервисного взаимодействия
    flows_service_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("flows_service_url"),
        description="Внутренний или dev URL сервиса flows (ServiceClient, локальные вызовы).",
    )
    flows_webhook_public_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("flows_webhook_public_base_url"),
        description=(
            "Явный публичный origin без завершающего слэша для setWebhook (если отличается от "
            "канона ingress). Если пусто — {platform_public_base_url}/flows, иначе flows_service_url."
        ),
    )
    crm_service_url: str | None = None
    frontend_service_url: str | None = None
    rag_service_url: str | None = None
    sync_service_url: str | None = None
    scheduler_service_url: str | None = None
    office_service_url: str | None = None
    worktracker_service_url: str | None = None
    secrets_service_url: str | None = None
    browser_service_url: str | None = None
    search_service_url: str | None = None
    wiki_service_url: str | None = None
    stock_service_url: str | None = None
    shop_service_url: str | None = None
    geo_service_url: str | None = None
    guest_runtime_service_url: str | None = None
    realtime_service_url: str | None = None
    provider_litserve_service_url: str | None = None
    voice_service_url: str | None = None
    capability_gateway_service_url: str | None = None
    code_runner_python_service_url: str | None = None
    code_runner_node_service_url: str | None = None
    code_runner_go_service_url: str | None = None
    code_runner_csharp_service_url: str | None = None
    platform_public_base_url: str | None = Field(
        default="https://linnex.io",
        description=(
            "Публичный origin без завершающего слэша (primary apex): "
            "NotificationURL Т-Банка, short links, календарь, Sync join."
        ),
    )
    document_server_dev_upstream_url: str | None = Field(
        default=None,
        description=(
            "development/test: реальный HTTP origin Document Server для DevInterServiceProxy "
            "(/web-apps, /common, /cache, /fonts, /sdkjs). Публичный origin в editor-config — "
            "office.document_server_public_url (тот же host, что shell, например :8002)."
        ),
    )

    # Порты по умолчанию для каждого сервиса
    _default_ports: ClassVar[dict[str, int]] = {
        "flows": 8001,
        "frontend": 8002,
        "crm": 8003,
        "rag": 8004,
        "sync": 8005,
        "scheduler": 8006,
        "office": 8008,
        "browser": 8009,
        "search": 8010,
        "provider_litserve": 8014,
        "voice": 8015,
        "capability_gateway": 8016,
        "code_runner_python": 8017,
        "code_runner_node": 8018,
        "code_runner_go": 8019,
        "code_runner_csharp": 8020,
        "worktracker": 8021,
        "secrets": 8022,
        "wiki": 8023,
        "guest_runtime": 8024,
        "realtime": 8025,
        "stock": 8026,
        "shop": 8027,
        "geo": 8028,
    }

    def get_service_url(self, service: str | None = None) -> str:
        """
        Возвращает URL сервиса.

        Аргументы:
            service: Имя сервиса (flows, crm, office, …). Если None — URL текущего сервиса.
        """
        if service is None:
            return f"http://localhost:{self.port}"

        url = self._configured_service_url(service)
        if url is not None and url.strip():
            return url.strip()

        default_port = self._default_ports[service]
        if service == "provider_litserve":
            return f"http://127.0.0.1:{default_port}"
        return f"http://localhost:{default_port}"

    def _configured_service_url(self, service: str) -> str | None:
        match service:
            case "flows":
                return self.flows_service_url
            case "frontend":
                return self.frontend_service_url
            case "crm":
                return self.crm_service_url
            case "rag":
                return self.rag_service_url
            case "sync":
                return self.sync_service_url
            case "scheduler":
                return self.scheduler_service_url
            case "office":
                return self.office_service_url
            case "worktracker":
                return self.worktracker_service_url
            case "secrets":
                return self.secrets_service_url
            case "browser":
                return self.browser_service_url
            case "search":
                return self.search_service_url
            case "wiki":
                return self.wiki_service_url
            case "stock":
                return self.stock_service_url
            case "shop":
                return self.shop_service_url
            case "geo":
                return self.geo_service_url
            case "guest_runtime":
                return self.guest_runtime_service_url
            case "realtime":
                return self.realtime_service_url
            case "provider_litserve":
                return self.provider_litserve_service_url
            case "voice":
                return self.voice_service_url
            case "capability_gateway":
                return self.capability_gateway_service_url
            case "code_runner_python":
                return self.code_runner_python_service_url
            case "code_runner_node":
                return self.code_runner_node_service_url
            case "code_runner_go":
                return self.code_runner_go_service_url
            case "code_runner_csharp":
                return self.code_runner_csharp_service_url
            case _:
                raise ValueError(f"Unknown service: {service}")

    def get_flows_service_url(self) -> str:
        """URL сервиса flows."""
        return self.get_service_url("flows")

    def get_flows_webhook_public_base_url(self) -> str:
        """
        Публичный базовый URL для webhook flows (Telegram setWebhook).

        Приоритет: flows_webhook_public_base_url → {platform_public_base_url}/flows
        (совпадает с ingress path `/flows`) → flows_service_url.
        """
        if self.flows_webhook_public_base_url:
            return str(self.flows_webhook_public_base_url).rstrip("/")
        pub = self.platform_public_base_url
        if pub is not None:
            trimmed = str(pub).strip()
            if trimmed:
                return f"{trimmed.rstrip('/')}/flows"
        return self.get_flows_service_url().rstrip("/")


class WorkerConfig(BaseModel):
    """Конфигурация воркеров"""

    max_workers: int = 4
    task_poll_interval: int = 5

    """Конфигурация FASHN API"""

    enabled: bool = False
    api_key: str | None = None
    base_url: str = "https://api.fashn.ai/v1"
    timeout: int = 120
    poll_interval: float = 5.0
    poll_timeout: int = 600


class CloudRuSTTConfig(BaseModel):
    """Конфигурация cloud.ru STT (Whisper API).

    Лимиты ffmpeg-чанков для batch-транскрипции задаются в
    `MediaTranscriberConfig`, не здесь.
    """

    enabled: bool = False
    api_key: str | None = None
    base_url: str = "https://foundation-models.api.cloud.ru/v1/audio/transcriptions"
    model: str = "openai/whisper-large-v3"
    response_format: str = "text"
    temperature: float = 0.5
    language: str = "ru"
    timeout: float = 120.0


# ---------------------------------------------------------------------------
# Унифицированные настройки провайдеров речи (STT/TTS/VAD).
#
# Один источник правды для voice/flows/eval/sync/CRM. Доступен в любом
# сервисе через `get_settings().voice`. Конкретный клиент достаётся
# через `core.clients.voice_resolver` с tier-резолвом
# tier-резолв (override -> company -> deployment-default).
# ---------------------------------------------------------------------------


class LitserveSpeechBackendConfig(BaseModel):
    """HTTP-настройки backend `provider-litserve` для STT/TTS/VAD."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str | None = Field(
        default=None,
        description=(
            "Явный override базового URL provider-litserve (без trailing slash) для "
            "/v1/audio/transcriptions, /v1/audio/speech, /v1/audio/vad. "
            "None — канонический ``server.provider_litserve_service_url`` "
            "(``provider_litserve_service_url()``)."
        ),
    )
    timeout_s: float = Field(
        default=120.0,
        gt=0.0,
        description=(
            "Таймаут HTTP к provider-litserve (секунды). Локальный Silero TTS на CPU может "
            "держать ответ дольше 60 с при холодном старте; при необходимости поднять через "
            "VOICE__STT__LITSERVE__TIMEOUT_S / VOICE__TTS__LITSERVE__TIMEOUT_S / VOICE__VAD__LITSERVE__TIMEOUT_S."
        ),
    )


class CloudRuTTSBackendConfig(BaseModel):
    """Cloud.ru TTS backend (OpenAI-совместимый /v1/audio/speech)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: str | None = None
    base_url: str = "https://foundation-models.api.cloud.ru/v1/audio/speech"
    model: str = "openai/tts-1"
    voice: str = "alloy"
    response_format: Literal["wav", "mp3", "ogg", "pcm"] = "mp3"
    sample_rate: int = Field(default=24000, gt=0)
    timeout_s: float = Field(default=120.0, gt=0.0)


class YandexSTTBackendConfig(BaseModel):
    """Yandex SpeechKit STT (REST). Stub до получения ключей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: str | None = None
    folder_id: str | None = None
    base_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    model: str = "general"
    timeout_s: float = Field(default=120.0, gt=0.0)


class YandexTTSBackendConfig(BaseModel):
    """Yandex SpeechKit TTS (REST). Stub до получения ключей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: str | None = None
    folder_id: str | None = None
    base_url: str = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    voice: str = "ermil"
    response_format: Literal["wav", "mp3", "ogg", "pcm", "lpcm"] = "lpcm"
    sample_rate: int = Field(default=48000, gt=0)
    timeout_s: float = Field(default=60.0, gt=0.0)


class SberSTTBackendConfig(BaseModel):
    """Sber SmartSpeech STT (REST). Stub до получения ключей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: str | None = None
    client_secret: str | None = None
    auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    base_url: str = "https://smartspeech.sber.ru/rest/v1/speech:recognize"
    scope: str = "SALUTE_SPEECH_PERS"
    model: str = "general"
    timeout_s: float = Field(default=120.0, gt=0.0)


class SberTTSBackendConfig(BaseModel):
    """Sber SmartSpeech TTS (REST). Stub до получения ключей."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: str | None = None
    client_secret: str | None = None
    auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    base_url: str = "https://smartspeech.sber.ru/rest/v1/text:synthesize"
    scope: str = "SALUTE_SPEECH_PERS"
    voice: str = "May_24000"
    response_format: Literal["wav", "mp3", "ogg", "pcm"] = "wav"
    sample_rate: int = Field(default=24000, gt=0)
    timeout_s: float = Field(default=60.0, gt=0.0)


class LocalSileroVADBackendConfig(BaseModel):
    """Локальный Silero VAD (in-process, без HTTP к provider-litserve)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    hf_model_id: str = "snakers4/silero-vad"
    sample_rate: int = Field(default=16000, gt=0)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_speech_ms: int = Field(default=300, ge=0)
    min_silence_ms: int = Field(default=500, ge=0)


class STTProvidersConfig(BaseModel):
    """Унифицированный конфиг STT для voice/flows/eval/sync.

    Поле `provider` — deployment-default (per-process). Per-company
    перекрывается записью в `company_voice_providers`, per-call — через
    `SpeechOverride`.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: SpeechProvider = "litserve"
    default_model: str | None = Field(
        default=None,
        description=(
            "OpenAI-совместимый id модели по умолчанию для выбранного "
            "провайдера (например `gigaam-v3` для litserve)."
        ),
    )
    default_language: str = "ru"
    mock_transcript_text: str = "Тестовая транскрипция"
    partial_transcripts_enabled: bool = Field(
        default=True,
        description=(
            "Слать клиенту WS-фреймы `transcript final=False` пока пользователь "
            "ещё говорит (chunked-batch peek_transcript). Выключение даст только "
            "финальный transcript после паузы."
        ),
    )
    partial_min_speech_frames: int = Field(
        default=50,
        ge=1,
        description=(
            "Минимум 20 ms-фреймов речи между двумя partial-вызовами "
            "`peek_transcript` (50 = ≈ 1 секунда речи)."
        ),
    )
    partial_min_buffer_ms: int = Field(
        default=500,
        ge=100,
        description=(
            "Минимальная длина PCM в буфере (ms), при которой имеет смысл "
            "запускать batch-распознавание для partial."
        ),
    )
    litserve: LitserveSpeechBackendConfig = Field(default_factory=LitserveSpeechBackendConfig)
    cloud_ru: CloudRuSTTConfig = Field(default_factory=CloudRuSTTConfig)
    yandex: YandexSTTBackendConfig = Field(default_factory=YandexSTTBackendConfig)
    sber: SberSTTBackendConfig = Field(default_factory=SberSTTBackendConfig)


class TTSPronunciationConfig(BaseModel):
    """Настройки TTS pronunciation shaping."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    ssml_subset_enabled: bool = False


class TTSProvidersConfig(BaseModel):
    """Унифицированный конфиг TTS для voice/flows/eval."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: SpeechProvider = "litserve"
    default_model: str | None = Field(
        default=None,
        description="OpenAI-совместимый id модели по умолчанию (например `qwen3-tts-1.7b-customvoice-ru`).",
    )
    default_voice: str | None = None
    default_response_format: Literal["wav", "mp3", "ogg", "pcm"] = "wav"
    default_sample_rate: int = Field(default=24000, gt=0)
    chunk_max_chars: int = Field(default=100, ge=1)
    lookahead_tokens: int = Field(default=20, ge=0)
    pronunciation_seed_enabled: bool = True
    pronunciation: TTSPronunciationConfig = Field(default_factory=TTSPronunciationConfig)
    litserve: LitserveSpeechBackendConfig = Field(default_factory=LitserveSpeechBackendConfig)
    cloud_ru: CloudRuTTSBackendConfig = Field(default_factory=CloudRuTTSBackendConfig)
    yandex: YandexTTSBackendConfig = Field(default_factory=YandexTTSBackendConfig)
    sber: SberTTSBackendConfig = Field(default_factory=SberTTSBackendConfig)


class VADProvidersConfig(BaseModel):
    """Унифицированный конфиг VAD для voice/flows/eval.

    Параметры streaming-VAD (`activation_threshold`, `deactivation_threshold`,
    `min_speech_ms`, `min_silence_ms`, `prefix_padding_ms`) совпадают с
    каноном LiveKit/Pipecat: гистерезис на вход/выход состояния SPEECH +
    подтверждение длительностью + pre-roll буфер для STT.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: VadProvider = "silero_local"
    default_model: str | None = None
    default_sample_rate: int = Field(default=16000, gt=0)
    default_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    echo_compensation: float = Field(default=0.2, ge=0.0, le=1.0)

    activation_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Порог prob для перехода SILENCE→SPEECH (LiveKit canon=0.5). "
            "Срабатывает в паре с `min_speech_ms`."
        ),
    )
    deactivation_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description=(
            "Порог prob ниже которого фрейм считается non-speech в state "
            "SPEECH (гистерезис, LiveKit canon = max(activation-0.15, 0.01)). "
            "Срабатывает в паре с `min_silence_ms`."
        ),
    )
    min_speech_ms: int = Field(
        default=50,
        ge=0,
        description=(
            "Минимум подтверждённой речи (мс), чтобы открыть VAD-окно. "
            "Защита от ложных стартов на щелчках/шумах."
        ),
    )
    min_silence_ms: int = Field(
        default=550,
        ge=0,
        description=(
            "Длительность непрерывной тишины (мс) для закрытия VAD-окна и "
            "финального flush в STT (LiveKit canon=550 мс)."
        ),
    )
    prefix_padding_ms: int = Field(
        default=500,
        ge=0,
        description=(
            "Pre-roll buffer (мс) — последние N мс PCM до VAD-start, "
            "которые при открытии VAD-окна доставляются в STT, чтобы не "
            "потерять первый звук фразы (LiveKit canon=500 мс)."
        ),
    )

    litserve: LitserveSpeechBackendConfig = Field(default_factory=LitserveSpeechBackendConfig)
    silero_local: LocalSileroVADBackendConfig = Field(default_factory=LocalSileroVADBackendConfig)


class VoiceDiagnosticsConfig(BaseModel):
    """Dev-only диагностика voice gateway.

    По умолчанию выключено: без явного пути в `uplink_dump_dir` ws_receiver
    не сохраняет аудио. Включать только в dev / staging для разбора жалоб
    «STT неверно распознал мои слова» — записывается тот же PCM, который
    уходит в STT-провайдер, после resampling и FIR-фильтра.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    uplink_dump_dir: str | None = Field(
        default=None,
        description=(
            "Директория для дампа сырого uplink PCM как WAV. None — выкл. "
            "Файлы `voice_uplink_<session_id>_<ts>.wav` создаются на закрытии "
            "WS-сессии."
        ),
    )
    uplink_dump_max_mb: int = Field(
        default=50,
        ge=1,
        description=("Жёсткий лимит размера одного дампа (MB); записи поверх лимита обрезаются."),
    )


class SpeechProvidersConfig(BaseModel):
    """Единый конфиг провайдеров речи (STT/TTS/VAD).

    Доступен в любом сервисе через `get_settings().voice` — это
    deployment-default. Конкретный клиент достаётся через
    `core.clients.voice_resolver.get_stt_client / get_tts_client /
    get_vad_client(*, company_id, override)`.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    stt: STTProvidersConfig = Field(default_factory=STTProvidersConfig)
    tts: TTSProvidersConfig = Field(default_factory=TTSProvidersConfig)
    vad: VADProvidersConfig = Field(default_factory=VADProvidersConfig)
    diagnostics: VoiceDiagnosticsConfig = Field(default_factory=VoiceDiagnosticsConfig)


class TelegramConfig(BaseModel):
    """Конфигурация Telegram ботов"""

    enabled: bool = True
    api_base: str = "https://api.telegram.org"
    bots: dict[str, str] = Field(default_factory=dict)


class NanoBananaConfig(BaseModel):
    """Конфигурация image generation / NanoBanana crop."""

    enabled: bool = False
    model: str = "google:gemini-3.1-flash-image"
    timeout: int = 120


class ProxyConfig(BaseModel):
    """Конфигурация прокси с умной ротацией - проблемные прокси уходят в конец"""

    enabled: bool = False
    proxies: list[str] = Field(
        default_factory=list,
        description="Список прокси URL: ['http://proxy1:8080', 'http://user:pass@proxy2:8080']",
    )
    connect_timeout: float = Field(
        default=4.0,
        description="Таймаут подключения к прокси (секунды)",
    )
    prefer_proxy_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        description="TTL Redis-ключа prefer-proxy для origin (секунды); каждая SET learn обязана использовать EX",
    )
    retry_http_401_via_proxy: bool = Field(
        default=False,
        description="В SMART при 401 повторять запрос через egress proxy (может маскировать неверный токен)",
    )

    _current_index: int = PrivateAttr(default=0)
    _last_used_proxy: str | None = PrivateAttr(default=None)

    def get_next_proxy(self) -> str | None:
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

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider_type: Literal["tinkoff"]
    enabled: bool = True
    terminal_key: str
    password: str
    api_url: str = "https://securepay.tinkoff.ru/v2"
    receipt_enabled: bool = True
    taxation: Literal["osn", "usn_income", "usn_income_outcome", "esn", "patent"] = (
        "usn_income_outcome"
    )


class PaymentProvidersConfig(BaseModel):
    """Конфигурация платежных провайдеров"""

    default_provider: str | None = None
    sync_enabled: bool = Field(
        default=False, description="Включена ли периодическая сверка транзакций"
    )
    sync_cron: str = Field(
        default="*/30 * * * *", description="Cron-расписание для сверки транзакций"
    )
    sync_pending_max_age_hours: int = Field(
        default=24,
        ge=1,
        description=(
            "Окно возраста pending для CheckOrder. Старше окна — один CheckOrder; "
            "если банк всё ещё не терминальный — failed."
        ),
    )
    sync_check_order_limit: int = Field(
        default=50,
        ge=1,
        description="Потолок CheckOrder (и истечения stale pending) за один payment_sync_tick",
    )
    providers: dict[str, PaymentProviderConfigEntry] = Field(
        default_factory=dict, description="Платежные провайдеры (tinkoff_main)"
    )


class EmbeddingApiConfig(BaseModel):
    """Эмбеддинг: ``model``, ``dimension``, ``base_url`` в форме OpenAI/OpenRouter (единый блок для всех провайдеров)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    model: str = "qwen/qwen3-embedding-0.6b"
    dimension: int = 1024
    # Явный override корня ``…/v1``: при ``provider=openrouter`` пусто — из ``llm``;
    # при ``provider=provider_litserve`` пусто — из ``server.provider_litserve_service_url`` + ``/v1``.
    base_url: str | None = None
    mrl_output_dimension: int | None = Field(
        default=None,
        gt=0,
        description=(
            "MRL-усечение: если задано, вектор обрезается до первых N измерений "
            + "и L2-нормализуется перед сохранением. Совпадение с dimension — плотный вектор без паддинга."
        ),
    )
    query_instruction: str | None = Field(
        default="Given a web search query, retrieve relevant passages that answer the query",
        description=(
            "Asymmetric instruct-префикс для поисковых запросов (Qwen3-Embedding и совместимые): "
            + "запрос оборачивается в 'Instruct: {task}\\nQuery: {query}', документы индексируются без префикса. "
            + "Пустая строка/None — выключено."
        ),
    )


class EmbeddingConfig(BaseModel):
    """Конфигурация embedding: ``provider`` и вложенный блок ``api`` (``model``, ``dimension``, опционально ``base_url``)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = "provider_litserve"
    mock: bool = Field(
        default=False,
        description="Детерминированный embedding-клиент без внешнего API. В тестовом контуре включён и без этого флага.",
    )
    api: EmbeddingApiConfig = Field(default_factory=EmbeddingApiConfig)

    @field_validator("provider")
    @classmethod
    def _provider_supports_embedding(cls, value: str) -> str:
        return validate_platform_provider_for_capability(value, AICapability.EMBEDDING)


class RAGProviderConfig(BaseModel):
    """Конфигурация одного RAG провайдера"""

    enabled: bool = False
    api_key: str | None = None  # API ключ провайдера (например Agentset API)
    base_url: str | None = None
    timeout: int = 60

    # Специфика PgVector
    db_url: str | None = None

    # Provider-level ключ эмбеддингов pgvector; иначе используется ключ активного LLM provider.
    embedding_api_key: str | None = None
    # Средняя цена за 1M токенов (в рублях). ~$0.05 ≈ 5₽
    embedding_cost_per_1m_tokens: float = 5.0
    # Наценка платформы на embedding (1.1 = +10%)
    embedding_platform_markup: float = 1.1

    extra_params: JsonObject = Field(default_factory=dict)


class RerankerApiRuntimeConfig(BaseModel):
    """
    HTTP-реранкер: таймаут и опционально полный URL эндпоинта (override).

    При ``provider=provider_litserve`` URL по умолчанию строится из ``server.provider_litserve_service_url`` + ``/v1/rerank``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    base_url: str | None = None
    timeout_seconds: float = 60.0


class RerankerRuntimeConfig(BaseModel):
    """Реранкер: explicit enabled flag plus provider/model runtime config."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: str = "provider_litserve"
    api: RerankerApiRuntimeConfig | None = Field(default_factory=RerankerApiRuntimeConfig)
    # Биллинг: span rerank.{model} с quantity в токенах (tiktoken), цена из billing.resource_base_prices.rerank
    billing_model_id: str = "rerank"

    @field_validator("provider")
    @classmethod
    def _provider_supports_rerank(cls, value: str) -> str:
        return validate_platform_provider_for_capability(value, AICapability.RERANK)

    @model_validator(mode="after")
    def _require_api_object_for_provider_litserve(self) -> Self:
        if self.provider == "provider_litserve" and self.api is None:
            raise ValueError('rag.reranker.api is required for provider_litserve')
        return self

    @property
    def base_url(self) -> str | None:
        if not self.enabled or self.api is None:
            return None
        u = self.api.base_url
        if u is None or not str(u).strip():
            return None
        return str(u).strip()

    @property
    def timeout_seconds(self) -> float:
        if self.enabled and self.api is not None:
            return float(self.api.timeout_seconds)
        return 60.0


class ProviderLitserveSTTModelEntry(BaseModel):
    """Описание одной STT-модели провайдера (api id ↔ HF id + параметры весов)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_model_id: str = Field(
        description="OpenAI-совместимый id модели (используется в payload поля model).",
    )
    hf_model_id: str = Field(
        description="HuggingFace repo id для скачивания весов.",
    )
    revision: str | None = Field(
        default=None,
        description="HF-ветка/тэг (например, e2e_rnnt для GigaAM v3).",
    )
    backend: Literal["gigaam", "huggingface_ctc", "whisper"] = Field(
        default="gigaam",
        description=(
            "Выбор runtime-адаптера для модели: gigaam (AutoModel + trust_remote_code + "
            ".transcribe()), huggingface_ctc (AutoProcessor + AutoModelForCTC), "
            "whisper (AutoModelForSpeechSeq2Seq pipeline)."
        ),
    )


# Спикеры checkpoint-а ``Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`` (``talker_config.spk_id``).
QWEN3_TTS_CUSTOM_VOICE_SPEAKERS: frozenset[str] = frozenset(
    (
        "aiden",
        "dylan",
        "eric",
        "ono_anna",
        "ryan",
        "serena",
        "sohee",
        "uncle_fu",
        "vivian",
    )
)

# ISO 639-1 → имя языка в API ``generate_custom_voice`` (``codec_language_id`` модели).
QWEN3_TTS_LANGUAGE_BY_LOCALE: dict[str, str] = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
}

# Частоты ответа локального TTS: нативный выход модели 24 kHz ресемплируется в любую из них.
LITSERVE_TTS_SAMPLE_RATE_IDS: tuple[int, ...] = (8000, 16000, 24000, 44100, 48000)


class ProviderLitserveTTSModelEntry(BaseModel):
    """Описание одной TTS-модели Qwen3-TTS CustomVoice (api id ↔ HF id + параметры синтеза)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_model_id: str
    hf_model_id: str
    revision: str | None = None
    voice: str | None = Field(
        default=None,
        description=(
            "Спикер по умолчанию из ``QWEN3_TTS_CUSTOM_VOICE_SPEAKERS`` "
            "(например ``serena``, ``vivian``)."
        ),
    )
    synthesis_locale: str | None = Field(
        default=None,
        description=(
            "ISO 639-1 (две буквы): язык синтеза из ``QWEN3_TTS_LANGUAGE_BY_LOCALE``. "
            "При совпадении с языком сессии TTS в voice_resolver "
            "(query `language` WebSocket или company_voice_providers.tts) выбирается эта запись "
            "каталога вместо tier-default."
        ),
    )
    sample_rate: int | None = Field(
        default=None,
        description=(
            "Sample rate ответа по умолчанию из ``LITSERVE_TTS_SAMPLE_RATE_IDS`` "
            "(нативный выход модели 24 kHz ресемплируется)."
        ),
    )
    instruct: str | None = Field(
        default=None,
        description="Стилевая инструкция CustomVoice по умолчанию (эмоция, темп, манера).",
    )
    tts_input_steps: tuple[str, ...] = Field(
        default=(),
        description=(
            "Именованные шаги подготовки текста после Unicode-нормализации на стороне LitServe. "
            "Реестр шагов — ``core.utils.tts_input_steps.TTS_INPUT_STEP_REGISTRY``."
        ),
    )

    @field_validator("voice", mode="before")
    @classmethod
    def trim_lower_voice_optional(cls, v: JsonValue) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f"TTS voice: expected str or None, got {type(v).__name__}")
        s = v.strip().lower()
        if not s:
            return None
        return s

    @field_validator("synthesis_locale", mode="before")
    @classmethod
    def synthesis_locale_iso639(cls, v: JsonValue) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(
                f"TTS synthesis_locale: expected str or None, got {type(v).__name__}"
            )
        s = v.strip().lower()
        if s == "":
            return None
        base = s.split("-")[0].split("_")[0]
        if len(base) < 2:
            raise ValueError('TTS synthesis_locale: ISO 639-1 required (at least 2 letters)')
        return base[:2]

    @field_validator("instruct", mode="before")
    @classmethod
    def trim_instruct_optional(cls, v: JsonValue) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f"TTS instruct: expected str or None, got {type(v).__name__}")
        s = v.strip()
        return s or None

    @field_validator("tts_input_steps", mode="before")
    @classmethod
    def normalize_tts_input_steps(cls, v: JsonValue) -> tuple[str, ...]:
        if v is None:
            return ()
        if isinstance(v, str):
            raise ValueError('tts_input_steps: expected a tuple or list of step names, not str')
        if not isinstance(v, list | tuple):
            raise ValueError(
                f"tts_input_steps: expected tuple or list, got {type(v).__name__}"
            )
        out: list[str] = []
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(
                    f"tts_input_steps[{i}]: expected str, got {type(item).__name__}"
                )
            s = item.strip()
            if s == "":
                raise ValueError(f"tts_input_steps[{i}]: empty string")
            out.append(s)
        return tuple(out)

    @model_validator(mode="after")
    def sample_rate_must_be_supported(self) -> Self:
        if self.sample_rate is None:
            return self
        if self.sample_rate not in LITSERVE_TTS_SAMPLE_RATE_IDS:
            allowed = ", ".join(str(sr) for sr in LITSERVE_TTS_SAMPLE_RATE_IDS)
            raise ValueError(f"TTS sample_rate={self.sample_rate}: allowed: {allowed}")
        return self

    @model_validator(mode="after")
    def voice_must_be_custom_voice_speaker(self) -> Self:
        if self.voice is None:
            return self
        if self.voice not in QWEN3_TTS_CUSTOM_VOICE_SPEAKERS:
            allowed = ", ".join(sorted(QWEN3_TTS_CUSTOM_VOICE_SPEAKERS))
            raise ValueError(f"TTS voice={self.voice!r}: allowed: {allowed}")
        return self

    @model_validator(mode="after")
    def synthesis_locale_must_be_supported(self) -> Self:
        if self.synthesis_locale is None:
            return self
        if self.synthesis_locale not in QWEN3_TTS_LANGUAGE_BY_LOCALE:
            allowed = ", ".join(sorted(QWEN3_TTS_LANGUAGE_BY_LOCALE))
            raise ValueError(
                f"TTS synthesis_locale={self.synthesis_locale!r}: allowed: {allowed}"
            )
        return self

    @model_validator(mode="after")
    def tts_input_steps_must_be_registered(self) -> Self:
        unknown = [s for s in self.tts_input_steps if s not in TTS_INPUT_STEP_IDS]
        if unknown:
            allowed = ", ".join(sorted(TTS_INPUT_STEP_IDS))
            raise ValueError(
                f"tts_input_steps: unknown steps {unknown}; registered: {allowed}"
            )
        return self


class ProviderLitserveVADModelEntry(BaseModel):
    """Описание одной VAD-модели (api id ↔ HF id + параметры детекции)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_model_id: str
    hf_model_id: str
    revision: str | None = None
    backend: Literal["silero"] = Field(
        default="silero",
        description="Runtime-адаптер VAD (silero). Расширяется по мере добавления моделей.",
    )
    sample_rate: int | None = Field(
        default=None,
        ge=8000,
        le=48000,
        description="Ожидаемый sample rate входного PCM.",
    )
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Порог уверенности для определения речи.",
    )


class TextTransformsConfig(BaseModel):
    """Платформенные настройки текстовых трансформаций поверх company LLM capabilities."""

    markdown_max_chunk_chars: int = Field(
        default=6000,
        ge=512,
        le=100_000,
        description="Максимум символов на чанк перед LLM-format Markdown.",
    )
    markdown_chunk_join: str = Field(
        default="\n\n",
        description="Склейка между отформатированными markdown-чанками.",
    )


class ProviderLitserveInfraConfig(BaseModel):
    """
    Деплой локального OpenAI-совместимого LitServe: один HTTP-порт, локальные не-LLM воркеры.

    Относится к процессу ``apps.provider_litserve.main``, не к доменному ``rag.reranker``.
    Переопределение деплоя: ``services.provider_litserve``; ENV: ``PROVIDER_LITSERVE__INFRA__*``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    backend: Literal["placeholder", "flagllm"] = "flagllm"
    host: str = "0.0.0.0"
    gateway_port: int = 8014
    accelerator: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        description=(
            "Устройство воркеров LitServe: auto — CUDA при доступности torch.cuda иначе CPU (или MPS на Apple); "
            "cuda — cuda:0; на GPU-ноде с Docker передайте через compose --gpus и драйвер на хосте."
        ),
    )
    embedding_accelerator: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        description=(
            "Устройство только для POST /v1/embeddings (SentenceTransformer). "
            "auto — то же, что выбрано глобальным accelerator для воркера; "
            "cpu — принудительно RAM/CPU (если эмбеддер не помещается в VRAM)."
        ),
    )
    rerank_accelerator: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        description=(
            "Устройство только для POST /v1/rerank (FlagLLM реранкер). "
            "auto — то же, что глобальный accelerator для воркера; "
            "cpu — принудительно CPU (разгрузка VRAM под STT на малой карте)."
        ),
    )
    workers_per_device: int = 1
    request_timeout_seconds: float = 300.0
    fast_queue: bool = False

    max_passages: int = 128
    max_query_chars: int = 16384
    max_passage_chars: int = 64000
    max_length: int = 8192
    model_batch_size: int = 4
    rerank_model_id: str = "Qwen/Qwen3-Reranker-0.6B"

    use_fp16: bool = True
    use_bf16: bool = False
    normalize_scores: bool = True

    embedding_use_bf16: bool = Field(
        default=True,
        description=(
            "Загружать SentenceTransformer (embedding) в bfloat16 вместо fp32. "
            "Экономит ~50%% VRAM (2.3 GB → ~1.2 GB) при незначительном изменении точности. "
            "Требует CUDA и поддержки bf16 картой (Ampere+). При cpu-девайсе игнорируется."
        ),
    )

    embedding_model_id: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_openai_model_id: str = "qwen/qwen3-embedding-0.6b"
    rerank_openai_model_id: str = "qwen/qwen3-reranker-0.6b"
    embedding_model_ids: list[str] = Field(default_factory=list)
    rerank_model_ids: list[str] = Field(default_factory=list)
    embedding_dimension: int | None = None

    stt_models: list["ProviderLitserveSTTModelEntry"] = Field(
        default_factory=lambda: [
            ProviderLitserveSTTModelEntry(
                api_model_id="gigaam-v3-rnnt-ru",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
            ),
        ],
        description=(
            "Полный список STT-моделей провайдера. Каждый элемент описывает одну модель "
            "(api id для /v1/audio/transcriptions, hf id для весов, опциональная revision). "
            "Дефолт — самая старая ready-запись каталога. Расширяется из UI /litserve/models."
        ),
    )
    tts_models: list["ProviderLitserveTTSModelEntry"] = Field(
        default_factory=lambda: [
            ProviderLitserveTTSModelEntry(
                api_model_id="qwen3-tts-1.7b-customvoice-ru",
                hf_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                voice="serena",
                synthesis_locale="ru",
                sample_rate=24000,
            ),
        ],
        description=(
            "Полный список TTS-моделей провайдера. Каждый элемент описывает одну модель "
            "(api id для /v1/audio/speech, hf id весов, voice, synthesis_locale, sample_rate). "
            "Дефолт — самая старая ready-запись каталога. Расширяется из UI /litserve/models."
        ),
    )
    vad_models: list["ProviderLitserveVADModelEntry"] = Field(
        default_factory=lambda: [
            ProviderLitserveVADModelEntry(
                api_model_id="silero-vad-v5",
                hf_model_id="snakers4/silero-vad",
                sample_rate=16000,
                threshold=0.5,
            ),
        ],
        description=(
            "Полный список VAD-моделей провайдера. Каждый элемент описывает одну модель "
            "(api id для /v1/audio/vad, hf id, sample_rate, threshold). "
            "Дефолт — самая старая ready-запись каталога. Расширяется из UI /litserve/models."
        ),
    )
    enabled_workers: list[Literal["embedding", "rerank", "stt", "tts", "vad"]] = Field(
        default_factory=list,
        description="Явный список LitServe-воркеров процесса. Пусто — embedding/rerank/stt/tts/vad.",
    )

    hf_token: str | None = None


class ProviderLitserveConfig(BaseModel):
    """Локальные модели LitServe: embeddings, rerank, speech."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    infra: ProviderLitserveInfraConfig = Field(default_factory=ProviderLitserveInfraConfig)
    lit_server_api_key: str | None = Field(
        default=None,
        description=(
            "Ключ для ``Authorization: Bearer`` на ``/v1`` provider_litserve. На самом поде "
            "его проверяет LitServe (env ``LIT_SERVER_API_KEY``); здесь — клиентская копия "
            "для platform-клиентов (voice/embedding/rerank/models list). Пусто — ``/v1`` без ключа."
        ),
    )


class RagTtlConfig(BaseModel):
    """
    TTL по умолчанию, параметры фоновой очистки и перевекторизации документов RAG.

    Клиент задаёт время жизни через ``ttl_seconds`` в metadata при загрузке;
    ``0`` — бессрочно. Если ключ отсутствует, применяется ``default_ttl_seconds``.
    Джобы планируются процессом ``scheduler``, исполняются в очереди ``rag``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

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
    reembed_enabled: bool = Field(
        default=True,
        description="Фоновая перевекторизация чанков с embedding_model IS NULL.",
    )
    reembed_cron: str = Field(
        default="*/5 * * * *",
        description="Cron (UTC) для тика перевекторизации устаревших чанков.",
    )
    reembed_batch_size: int = Field(
        default=50,
        ge=1,
        le=2000,
        description="Максимум чанков за один тик перевекторизации.",
    )
    orphan_cleanup_enabled: bool = Field(
        default=True,
        description="Фоновое удаление чанков vector_documents без company_id (orphan).",
    )
    orphan_cleanup_cron: str = Field(
        default="*/15 * * * *",
        description="Cron (UTC) для тика чистки orphan-чанков без company_id.",
    )
    orphan_cleanup_batch_size: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Максимум orphan-чанков (company_id IS NULL/'') за один тик.",
    )


class RAGConfig(BaseModel):
    """Конфигурация RAG системы"""

    enabled: bool = False
    default_provider: str = "agentset"

    # Общая конфигурация embeddings для всех провайдеров
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

    providers: dict[str, RAGProviderConfig] = Field(default_factory=dict)
    reranker: RerankerRuntimeConfig = Field(default_factory=RerankerRuntimeConfig)
    document_indexing: IndexProfileConfig = Field(
        default_factory=IndexProfileConfig,
        description="Парсинг, нарезка, lexical/search_defaults для индексации и поиска (без БД-профилей).",
    )
    index_profiles: dict[str, IndexProfileConfig] = Field(
        default_factory=dict,
        description="Именованные профили индексации (runet_web и др.).",
    )
    ttl: RagTtlConfig = Field(
        default_factory=RagTtlConfig,
        description="TTL индексируемых документов и периодическая очистка.",
    )

    def get_enabled_provider_key(self, override: str | None = None) -> str:
        """Имя провайдера из ``override`` или ``default_provider`` с проверкой ``rag.enabled`` и ``providers[name].enabled``."""
        if not self.enabled:
            raise ValueError('RAG is disabled in configuration (rag.enabled = false)')
        key = (override if override is not None else self.default_provider).strip()
        if not key:
            raise ValueError('rag.default_provider is empty')
        if key not in self.providers:
            available = ", ".join(sorted(self.providers.keys()))
            raise ValueError(f"Unknown RAG provider: {key}. Available: {available}")
        pcfg = self.providers[key]
        if not pcfg.enabled:
            raise ValueError(f"Provider {key} is disabled (enabled = false)")
        return key


class SGRConfig(BaseModel):
    """Конфигурация SGR Deep Research сервиса"""

    enabled: bool = False
    base_url: str = "http://localhost:8010"
    api_key: str | None = None
    timeout: float = 300.0
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 8000
    llm_temperature: float = 0.4
    tavily_api_key: str | None = None
    max_steps: int = 6
    max_results: int = 10


class TracingConfig(BaseModel):
    """Конфигурация трейсинга"""

    enabled: bool = True
    service_name: str = "agent-lab"
    postgres_enabled: bool = True
    tempo_enabled: bool = False
    tempo_endpoint: str = "http://localhost:4317"
    otlp_endpoint: str = Field(
        default="",
        description=(
            "OTLP gRPC endpoint (Alloy). Непустое значение включает экспорт spans. "
            "Пусто — tempo_endpoint, если tempo_enabled."
        ),
    )
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


def _default_stream_maxlen_by_queue() -> dict[str, int]:
    return {
        "search": 50_000,
        "idle": 20_000,
        "a2a_push": 20_000,
        "crm": 20_000,
        "crm_summary": 20_000,
        "rag": 20_000,
        "flows_worker": 10_000,
    }


class TasksConfig(BaseModel):
    """Конфигурация TaskIQ"""

    broker_url: str = "redis://localhost:6379/0"
    result_backend_url: str | None = None
    max_workers: int = 4
    default_retry_count: int = Field(
        default=3,
        ge=1,
        le=100,
        description=(
            "Верхняя граница повторов SimpleRetryMiddleware, когда у задачи нет метки max_retries "
            "(fallback через labels таска)."
        ),
    )
    stream_maxlen_by_queue: dict[str, int] = Field(
        default_factory=_default_stream_maxlen_by_queue,
        description="XADD maxlen per TaskIQ queue (approximate trim). Пустое значение очереди — без trim.",
    )
    stream_maxlen_default: int | None = Field(
        default=None,
        description="maxlen для очередей вне stream_maxlen_by_queue; None — без trim.",
    )


class OpenFGAConfig(BaseModel):
    """OpenFGA — единый PDP платформы (один store на всю платформу)."""

    enabled: bool = Field(
        default=False,
        description="Включает AuthzService checks/writes. После bootstrap store — true.",
    )
    api_url: str = Field(
        default="http://127.0.0.1:9090",
        description="HTTP API OpenFGA (не публиковать наружу).",
    )
    store_id: str = Field(
        default="",
        description="Id единственного store платформы (не company_id).",
    )
    authorization_model_id: str = Field(
        default="",
        description="Pinned authorization model id после bootstrap.",
    )
    api_token: str | None = Field(
        default=None,
        description="Preshared token OpenFGA (Authorization: Bearer).",
    )
    timeout_ms: int = Field(default=30_000, ge=100, description="Timeout OpenFGA client.")
    default_consistency: str = Field(
        default="MINIMIZE_LATENCY",
        description=(
            "AuthzConsistency default для Check/List/Expand/Read: "
            "MINIMIZE_LATENCY | HIGHER_CONSISTENCY."
        ),
    )


class EventsConfig(BaseModel):
    """Единая шина событий платформы (Redis Stream `platform:events`)."""

    stream_maxlen: int = Field(
        default=100_000,
        ge=1_000,
        description="XADD maxlen стрима platform:events (approximate trim).",
    )
    consumer_block_ms: int = Field(
        default=5_000,
        ge=100,
        description="BLOCK для XREAD/XREADGROUP потребителей шины.",
    )
    autoclaim_idle_ms: int = Field(
        default=120_000,
        ge=1_000,
        description="Порог idle для XAUTOCLAIM pending-записей мёртвых consumers.",
    )


class LanesConfig(BaseModel):
    """Строгие полосы исполнения команд (`core/lanes`)."""

    lock_timeout_ms: int = Field(
        default=3_000,
        ge=100,
        le=30_000,
        description="lock_timeout транзакции полосы; превышение — ошибка lane_busy, повтор с тем же idempotency_key безопасен.",
    )
    commit_retention_days: int = Field(
        default=14,
        ge=1,
        description="Сколько дней хранится опубликованный LaneCommit — окно идемпотентного повтора команды.",
    )
    relay_after_seconds: int = Field(
        default=10,
        ge=1,
        description="Возраст неопубликованного LaneCommit, после которого его события публикует relay.",
    )


class RealtimeConfig(BaseModel):
    """Bus `realtime` и HTTP API Centrifugo (единственный HTTP-peer CF)."""

    centrifugo_api_url: str = Field(
        default="http://127.0.0.1:8000/api",
        description="Базовый URL HTTP API Centrifugo, включая путь /api.",
    )
    centrifugo_api_key: str | None = Field(
        default=None,
        description="Ключ http_api.key Centrifugo. Только процесс realtime.",
    )
    command_deadline_seconds: int = Field(
        default=30,
        ge=1,
        description="Deadline обработки *_requested в логе bus.",
    )
    sweeper_interval_seconds: float = Field(
        default=5.0,
        ge=1.0,
        description="Интервал sweeper'а просроченных команд.",
    )


class CalendarSyncConfig(BaseModel):
    """Конфигурация фоновой синхронизации календаря."""

    enabled: bool = True
    cron: str = "*/15 * * * *"
    lookback_days: int = 7
    lookahead_months: int = 3
    batch_size: int = 100
    max_integrations_per_tick: int = 1000
    max_parallel_integrations: int = 10
    notification_dedup_ttl_seconds: int = 86400
    sync_meeting_reminder_enabled: bool = True
    sync_meeting_reminder_cron: str = "*/15 * * * *"
    sync_meeting_reminder_limit: int = 500
    autolink_enabled: bool = True
    autolink_well_known_probe_enabled: bool = True
    autolink_probe_timeout_seconds: float = 5.0


class MailSyncConfig(BaseModel):
    """Фоновая синхронизация IMAP-курсоров и notify о новых письмах."""

    enabled: bool = True
    cron: str = "*/1 * * * *"
    batch_size: int = 200
    max_bindings_per_tick: int = 2000
    max_parallel_bindings: int = 20
    max_new_messages_per_binding: int = 50
    max_drain_continuations: int = 10
    backfill_batch_size: int = 50
    reconcile_every_n_syncs: int = 1
    notification_dedup_ttl_seconds: int = 86400
    auth_error_cooldown_seconds: int = 3600
    idle_enabled: bool = True
    max_idle_bindings: int = 50
    idle_reconnect_seconds: int = 30
    idle_timeout_seconds: int = 1740


class MailIspmanagerConfig(BaseModel):
    """ISPmanager API для provision ящиков."""

    base_url: str | None = None
    authinfo_user: str | None = None
    authinfo_password: str | None = None


class MailSystemConfig(BaseModel):
    """Auto-seed CompanyMailConnection для company_id=system."""

    enabled: bool = False
    mail_domain: str = "linnex.io"
    provider: str = "ispmanager"
    imap_host: str | None = None
    imap_port: int = 993
    smtp_host: str | None = None
    smtp_port: int = 465
    use_ssl: bool = True
    ispmanager: MailIspmanagerConfig = Field(default_factory=MailIspmanagerConfig)
    role_mailboxes: list[str] = Field(
        default_factory=lambda: ["support", "hr", "pr", "sales", "info", "noreply"]
    )
    user_local_part_strategy: str = "slug_unique"
    protected_local_parts: list[str] = Field(
        default_factory=lambda: ["support", "hr", "pr", "sales", "info", "noreply"]
    )


class MailLivePersonalConfig(BaseModel):
    """Opt-in live тесты против фиксированных personal IMAP/SMTP ящиков (не ISP provision).

    Пароли — только в mail.local_dev.mailbox_passwords[email].
    """

    enabled: bool = False
    imap_host: str = "imap.mail.ru"
    imap_port: int = 993
    smtp_host: str = "smtp.mail.ru"
    smtp_port: int = 465
    use_ssl: bool = True
    account_a: str = ""
    account_b: str = ""
    # Mail.ru выдаёт пароль внешнего приложения отдельно для календаря: почтовый
    # пароль CalDAV отклоняет. Пусто — live-тест проверяет только статус needs_password.
    calendar_app_password_a: str = ""


class MailLiveTestConfig(BaseModel):
    """Opt-in live тесты против реального mail-сервера."""

    enabled: bool = False
    mailbox_prefix: str = "plt-"
    allow_delete: bool = True
    personal: MailLivePersonalConfig = Field(default_factory=MailLivePersonalConfig)


class MailLocalDevConfig(BaseModel):
    """Локальная разработка против shared ISP без смены паролей на сервере.

    Пароли ящиков — только в conf.local.json / ENV (gitignored). IMAP/SMTP
    логин берёт plaintext отсюда; email.edit(passwd) на ISP не вызывается,
    пока mutate_remote_passwords=false.
    """

    enabled: bool = False
    mutate_remote_passwords: bool = False
    mailbox_passwords: dict[str, str] = Field(default_factory=dict)


class MailConfig(BaseModel):
    """Платформенная почта: system auto-seed + live test gates."""

    system: MailSystemConfig = Field(default_factory=MailSystemConfig)
    live_test: MailLiveTestConfig = Field(default_factory=MailLiveTestConfig)
    local_dev: MailLocalDevConfig = Field(default_factory=MailLocalDevConfig)


class GoogleWorkspaceSystemConfig(BaseModel):
    """Seed company-owned Google Workspace SA into integration_credentials for system."""

    enabled: bool = False
    service_account_json: str | None = None
    impersonate_email: str | None = None


class GoogleWorkspaceLiveTestConfig(BaseModel):
    """Opt-in live тесты против реального Google API."""

    enabled: bool = False
    access_token: str | None = None
    refresh_token: str | None = None


class GoogleWorkspaceApiBases(BaseModel):
    """
    Override Google API endpoint bases (tests / local emulator).

    None = production Google host for that surface.
    """

    sheets_base: str | None = None
    docs_base: str | None = None
    drive_base: str | None = None
    drive_upload_base: str | None = None
    token_uri: str | None = None


class GoogleWorkspaceConfig(BaseModel):
    """Google Workspace connector settings (credentials table, no extra schema)."""

    system: GoogleWorkspaceSystemConfig = Field(default_factory=GoogleWorkspaceSystemConfig)
    live_test: GoogleWorkspaceLiveTestConfig = Field(default_factory=GoogleWorkspaceLiveTestConfig)
    api_bases: GoogleWorkspaceApiBases = Field(default_factory=GoogleWorkspaceApiBases)


class OpenAIProviderConfig(BaseModel):
    """Конфигурация OpenAI провайдера"""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str | None = Field(default=None)
    models_url: str | None = Field(default=None)
    smoke_model: str | None = Field(default=LLM_PROVIDER_SMOKE_MODELS["openai"])


class OpenRouterProviderConfig(BaseModel):
    """Конфигурация OpenRouter провайдера"""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["openrouter"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["openrouter"])
    site_url: str = Field(default="https://platform.local")
    site_name: str = Field(default="platform")
    smoke_model: str | None = Field(default=LLM_PROVIDER_SMOKE_MODELS["openrouter"])


class BothubProviderConfig(BaseModel):
    """Конфигурация Bothub провайдера"""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["bothub"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["bothub"])
    smoke_model: str | None = Field(default=LLM_PROVIDER_SMOKE_MODELS["bothub"])


class GroqProviderConfig(BaseModel):
    """OpenAI-compatible Groq Cloud provider."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["groq"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["groq"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["groq"])


class CerebrasProviderConfig(BaseModel):
    """OpenAI-compatible Cerebras Inference provider."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["cerebras"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["cerebras"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["cerebras"])


class GoogleLLMProviderConfig(BaseModel):
    """Google Gemini API через OpenAI-compatible chat endpoint и native models catalog."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["google"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["google"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["google"])


class GitHubModelsProviderConfig(BaseModel):
    """GitHub Models REST API provider."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["github"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["github"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["github"])
    api_version: str = Field(default=GITHUB_MODELS_API_VERSION)


class HuggingFaceProviderConfig(BaseModel):
    """Hugging Face Inference Providers OpenAI-compatible router."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["huggingface"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["huggingface"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["huggingface"])


class NvidiaProviderConfig(BaseModel):
    """NVIDIA NIM hosted OpenAI-compatible API (integrate.api.nvidia.com)."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["nvidia"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["nvidia"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["nvidia"])


class MistralProviderConfig(BaseModel):
    """Mistral AI OpenAI-compatible API."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["mistral"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["mistral"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["mistral"])


class ZAIProviderConfig(BaseModel):
    """Z.AI GLM OpenAI-compatible API (api.z.ai/api/paas/v4)."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["zai"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["zai"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["zai"])


class SambaNovaProviderConfig(BaseModel):
    """SambaNova Cloud OpenAI-compatible API."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["sambanova"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["sambanova"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["sambanova"])


class DeepInfraProviderConfig(BaseModel):
    """DeepInfra OpenAI-compatible provider."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["deepinfra"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["deepinfra"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["deepinfra"])


class CailaProviderConfig(BaseModel):
    """Caila OpenAI-compatible provider (100+ моделей через единый API)."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    base_url: str = Field(default=LLM_PROVIDER_DEFAULT_BASE_URLS["caila"])
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["caila"])
    smoke_model: str = Field(default=LLM_PROVIDER_SMOKE_MODELS["caila"])


class YandexLLMProviderConfig(BaseModel):
    """Yandex Cloud Foundation Models (OpenAI-совместимый endpoint): Api-Key + x-folder-id."""

    api_key: str | None = Field(default=None)
    api_keys: list[str] | None = Field(default=None)
    folder_id: str | None = Field(
        default=None,
        description="Идентификатор каталога Yandex Cloud (заголовок x-folder-id)",
    )
    base_url: str = Field(default="https://llm.api.cloud.yandex.net/v1")
    models_url: str = Field(default=LLM_PROVIDER_DEFAULT_MODELS_URLS["yandex"])
    smoke_model: str | None = Field(default=None)


class ModelConfig(BaseModel):
    """Конфигурация модели — переопределение temperature/max_tokens/context_length."""

    temperature: float = Field(default=0.2)
    max_tokens: int | None = Field(default=None)
    context_length: int | None = Field(default=None, gt=0)


class PlatformFreePoolPaidFallbackConfig(BaseModel):
    """Paid reserve route used only after verified free candidates are unavailable."""

    provider: str = Field(default="openrouter")
    model: str = Field(default="qwen/qwen-2.5-7b-instruct")

    @field_validator("provider", "model", mode="before")
    @classmethod
    def _strip_required_string(cls, value: JsonValue) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('provider/model must be non-empty strings')
        return value.strip()

    @field_validator("provider")
    @classmethod
    def _provider_must_be_platform_llm_provider(cls, value: str) -> str:
        if value not in OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS:
            allowed = ", ".join(OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)
            raise ValueError(f"provider must be one of: {allowed}")
        return value


class PlatformFreePoolConfig(BaseModel):
    """Platform default-route via provider-neutral verified free model catalog."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True)
    cache_ttl_seconds: int = Field(
        default=3540,
        ge=60,
        description="TTL Redis-кэша verified free-моделей.",
    )
    refresh_interval_seconds: int = Field(
        default=3300,
        ge=60,
        description="Интервал scheduler-задачи обновления verified free-моделей.",
    )
    first_token_timeout_seconds: float = Field(
        default=20.0,
        ge=1.0,
        description="Сколько ждать первый полезный stream event до следующего кандидата.",
    )
    candidate_cooldown_seconds: float = Field(
        default=60.0,
        ge=0.0,
        description="Redis TTL cooldown модели после отказа до первого чанка; 429 берёт Retry-After.",
    )
    paid_fallback: PlatformFreePoolPaidFallbackConfig = Field(
        default_factory=PlatformFreePoolPaidFallbackConfig
    )
    max_candidates_per_provider: int = Field(default=20, ge=1, le=100)
    max_candidates_total: int = Field(default=50, ge=1, le=200)
    include_provider_router_as_last_free_fallback: bool = Field(default=True)

    @model_validator(mode="after")
    def _ttl_covers_refresh_interval(self) -> Self:
        if self.cache_ttl_seconds <= self.refresh_interval_seconds:
            raise ValueError(
                'llm.platform_free_pool.cache_ttl_seconds must be greater than refresh_interval_seconds'
            )
        return self


class LLMConfig(BaseModel):
    """Конфигурация LLM с поддержкой нескольких провайдеров"""

    provider: str = Field(
        default=LINNEX_LLM_PROVIDER,
        description=(
            "Провайдер: linnex_llm, openai, openrouter, bothub, "
            "yandex, groq, cerebras, google, github, huggingface, nvidia, mistral, "
            "zai, sambanova, deepinfra, caila"
        ),
    )
    default_model: str = Field(default=LINNEX_LLM_AUTO_MODEL)
    vision_model: str = Field(
        default=LINNEX_LLM_AUTO_MODEL,
        description="Модель для multimodal/vision запросов",
    )
    temperature: float = Field(default=0.2)
    max_tokens: int | None = Field(default=None)
    timeout: float = Field(default=300.0)
    openai: OpenAIProviderConfig | None = Field(default=None)
    openrouter: OpenRouterProviderConfig | None = Field(default=None)
    bothub: BothubProviderConfig | None = Field(default=None)
    yandex: YandexLLMProviderConfig | None = Field(default=None)
    groq: GroqProviderConfig | None = Field(default=None)
    cerebras: CerebrasProviderConfig | None = Field(default=None)
    google: GoogleLLMProviderConfig | None = Field(default=None)
    github: GitHubModelsProviderConfig | None = Field(default=None)
    huggingface: HuggingFaceProviderConfig | None = Field(default=None)
    nvidia: NvidiaProviderConfig | None = Field(default=None)
    mistral: MistralProviderConfig | None = Field(default=None)
    zai: ZAIProviderConfig | None = Field(default=None)
    sambanova: SambaNovaProviderConfig | None = Field(default=None)
    deepinfra: DeepInfraProviderConfig | None = Field(default=None)
    caila: CailaProviderConfig | None = Field(default=None)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    default_strategy: Literal["configured", "platform_free_pool"] = Field(
        default="platform_free_pool",
        description=(
            "Как выбирать модель при LLM-вызове без model/provider: configured — "
            "settings.llm.default_model; platform_free_pool — Redis-кэш verified free "
            "моделей провайдеров + paid_fallback."
        ),
    )
    platform_free_pool: PlatformFreePoolConfig = Field(default_factory=PlatformFreePoolConfig)


class S3Config(BaseModel):
    """Платформенное объектное хранилище (SeaweedFS кластера). Хранилища компаний — таблица object_storages."""

    enabled: bool = Field(default=False)
    endpoint_url: str | None = Field(default=None)
    region_name: str = Field(default="us-east-1")
    bucket_name: str = Field(default="files")
    access_key_id: str | None = Field(default=None)
    secret_access_key: str | None = Field(default=None)
    provider: str = Field(default="seaweedfs")
    path_style: bool = Field(default=True)


class FilesRetentionConfig(BaseModel):
    default_ttl_seconds: int = Field(default=864000, ge=0)
    flow_session_ttl_seconds: int = Field(default=1209600, ge=0)
    sync_speech_segment_ttl_seconds: int = Field(default=1209600, ge=0)
    browser_artifact_ttl_seconds: int = Field(default=2592000, ge=0)
    generated_ephemeral_ttl_seconds: int = Field(default=604800, ge=0)
    office_document_ttl_seconds: int = Field(default=31536000, ge=0)
    purge_enabled: bool = Field(default=True)
    purge_batch_size: int = Field(default=200, ge=1, le=1000)
    purge_cron: str = Field(default="0 * * * *")
    backfill_batch_size: int = Field(default=200, ge=1, le=1000)


class FilesConfig(BaseModel):
    retention: FilesRetentionConfig = Field(default_factory=FilesRetentionConfig)
    max_upload_bytes: int = Field(
        default=512 * 1024 * 1024,
        ge=1024,
        description="Максимальный размер одного файла (chunked upload).",
    )
    chunk_size_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=5 * 1024 * 1024,
        description="Размер части chunked upload (S3 multipart min 5 MiB кроме последней).",
    )
    upload_session_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        description="TTL Redis-сессии незавершённого chunked upload.",
    )


class GuestRuntimeFarmConfig(BaseModel):
    """Ферма code_agent: executor без auto-fallback."""

    executor: Literal["docker", "inprocess"] = Field(default="inprocess")
    idle_ttl_seconds: int = Field(default=60, ge=1, le=86400)
    max_lifetime_seconds: int = Field(default=86400, ge=1, le=86400)
    max_source_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_image_bytes: int = Field(default=int(1.5 * 1024 * 1024 * 1024), ge=1)
    company_image_budget_bytes: int = Field(default=3 * 1024 * 1024 * 1024, ge=1)
    max_leases_per_company: int = Field(default=2, ge=1)
    max_leases_cluster: int = Field(default=8, ge=1)
    max_concurrent_builds: int = Field(default=1, ge=1)
    guest_cpu: str = Field(default="500m")
    guest_memory: str = Field(default="512Mi")
    pids_limit: int = Field(default=256, ge=1)
    data_dir: str = Field(default="/tmp/guest-runtime")
    reaper_interval_seconds: int = Field(default=5, ge=1)
    log_lines_max: int = Field(default=2000, ge=1)

    @model_validator(mode="after")
    def idle_within_lifetime(self) -> Self:
        if self.idle_ttl_seconds > self.max_lifetime_seconds:
            raise ValueError(
                "guest_runtime.idle_ttl_seconds must be <= max_lifetime_seconds"
            )
        return self


class CodeRunnerSettings(BaseModel):
    """Пул и каталоги кэша code runner. Пустые пути — `<repo>/.cache`."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    python_workers: int | None = Field(
        default=None,
        ge=1,
        description="Пул Python worker. Пусто — от 2 до 8 по CPU.",
    )
    node_workers: int | None = Field(
        default=None,
        ge=1,
        description="Пул Node worker. Пусто — от 2 до 8 по CPU.",
    )
    go_workers: int | None = Field(
        default=None,
        ge=1,
        description="Параллельные сборки Go. Пусто — от 2 до 8 по CPU; заданное значение не ниже 2.",
    )
    csharp_workers: int | None = Field(
        default=None,
        ge=1,
        description="Параллельные сборки C#. Пусто — от 2 до 8 по CPU; заданное значение не ниже 2.",
    )
    lsp_cache: str = Field(
        default="",
        description="Корень кэша language server. Пусто — <repo>/.cache.",
    )
    python_sandbox_site: str = Field(
        default="",
        description="Target site-packages Python sandbox. Пусто — <repo>/.cache/code-runner-python-sandbox-site.",
    )
    node_sandbox_modules: str = Field(
        default="",
        description="Prefix npm-пакетов Node sandbox. Пусто — <repo>/.cache/code-runner-node-sandbox-modules.",
    )
    runtime_dir: str = Field(
        default="",
        description="Каталог managed runtime. Пусто — ~/.cache/agent-lab/runtimes.",
    )
    go_bin: str = Field(default="", description="Явный путь go. Пусто — runtime_dir/bin, затем PATH.")
    node_bin: str = Field(default="", description="Явный путь node. Пусто — runtime_dir/bin, затем PATH.")
    npm_bin: str = Field(default="", description="Явный путь npm. Пусто — runtime_dir/bin, затем PATH.")
    dotnet_bin: str = Field(
        default="",
        description="Явный путь dotnet. Пусто — runtime_dir/bin, затем PATH.",
    )


class MCPBrandingConfig(BaseModel):
    """Seed глобальных иконок MCP из git-бандла."""

    bundle_path: str = Field(
        default="apps/flows/mcp_branding/manifest.yaml",
        description="Путь к manifest.yaml относительно корня репозитория",
    )
    seed_after_crawl: bool = Field(
        default=True,
        description="После crawl registry создавать branding для новых catalog_id",
    )


class MCPCatalogConfig(BaseModel):
    """Глобальный catalog HTTPS MCP + provision в компании."""

    enabled: bool = Field(default=True)
    auto_provision: Literal["all_verified", "approved_only", "disabled"] = Field(
        default="disabled",
        description=(
            "Auto-provision catalog entries into company Installed. "
            "disabled = opt-in Store only (platform Browser/Search via ensure_default). "
            "approved_only = auto-tier for platform_approved entries; "
            "all_verified = auto-tier for all verified catalog entries."
        ),
    )
    registry_base_url: str = Field(default="https://registry.modelcontextprotocol.io")
    crawl_cron: str = Field(default="0 0 * * *")
    crawl_run_on_start: bool = Field(
        default=True,
        description="Запустить mcp_catalog_crawl_task сразу при старте scheduler-api",
    )
    resync_tools_cron: str = Field(default="0 0 * * *")
    verify_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    crawl_page_limit: int = Field(default=100, ge=1, le=500)
    max_verify_per_crawl: int = Field(default=100, ge=0, le=5000)
    allowlist_path: str = Field(
        default="apps/flows/mcp_catalog_allowlist.yaml",
        description="Путь к yaml allowlist относительно корня репозитория",
    )


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
        description="Таймаут httpx2 при скачивании байт сегмента по URL (не S3 SDK).",
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
                'poll_lock_refresh_interval_seconds must be less than poll_lock_ttl_seconds'
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
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_email: str = "admin@linnex.io"
    apns_team_id: str | None = None
    apns_key_id: str | None = None
    apns_private_key: str | None = None
    apns_bundle_id: str | None = None
    apns_use_sandbox: bool = False
    fcm_credentials_json: str | JsonObject | None = None
    fcm_project_id: str | None = None


class PublicSiteConfig(BaseModel):
    """Публичные настройки маркетингового слоя сайта (виджеты, аналитика, комьюнити)."""

    telegram_community_url: str | None = None
    yandex_metrika_id: str | None = None
    google_analytics_measurement_id: str | None = None


class GeoIpConfig(BaseModel):
    """IP→страна для SEO-аналитики посетителей (DB-IP Lite CSV внутри образа).

    База — gzipped CSV ``start_ip,end_ip,cc``; скачивается в Dockerfile
    (``ARG GEOIP_DB_VERSION``), тесты подменяют ``db_path`` на fixture.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    # False по умолчанию: база существует только в собранном образе, включается
    # в проде через app-conf.k8s-overlay.json (geoip.enabled=true).
    enabled: bool = False
    db_path: str = "/app/data/geoip/dbip-country.csv.gz"


class LegalConfig(BaseModel):
    """Публичные реквизиты оператора платформы (ООО «ЛАЙНЕКС»)."""

    company_name_ru: str = "ООО «ЛАЙНЕКС»"
    company_name_en: str = 'OBSCHESTVO S OGRANICHENNOI OTVETSTVENNOSTYU "LAINEKS"'
    legal_form_ru: str = "Общество с ограниченной ответственностью"
    legal_form_en: str = "Limited Liability Company"
    inn: str = "9717194941"
    kpp: str = "771701001"
    ogrn: str = "1267700280132"
    legal_address_ru: str = (
        "129515, Россия, г. Москва, вн.тер.г. муниципальный округ Останкинский, "
        "б-р Звёздный, д. 12, к. 1, кв. 48"
    )
    legal_address_en: str = (
        "129515, ROSSIYA, G.MOSKVA, VN.TER.G. MUNITSIPALNYI OKRUG OSTANKINSKII, "
        "B-R ZVEZDNYI, D. 12, K. 1, KV. 48"
    )
    contact_email: str = "info@linnex.io"
    support_email: str = "info@linnex.io"
    dpo_email: str = "info@linnex.io"
    phone: str = "+7 (953) 477-10-94"
    min_age: int = 18
    retention_logs: str = "12 months"
    retention_messages: str = "24 months"
    retention_accounts: str = "5 years after account closure"
    cloud_provider: str = "Yandex Cloud"
    cloud_region: str = "Russian Federation"
    analytics_tools: str = "Internal monitoring and product analytics"
    billing_provider: str = "T-Bank"
    bank_name_ru: str = "АО «ТБанк»"
    bank_name_en: str = "TBank JSC"
    bank_account: str = "40702810010002289174"
    bank_bik: str = "044525974"
    bank_correspondent_account: str = "30101810145250000974"
    bank_inn: str = "7710140679"
    bank_address_ru: str = "127287, г. Москва, ул. 2-я Хуторская, д. 38А, стр. 26"
    bank_address_en: str = "38A 2-ya Khutorskaya ul., Bld. 26, Moscow 127287, Russia"


class CustomerAuthTelegramBotConfig(BaseModel):
    """Платформенный Telegram-бот приёма контактов на бренд."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    bot_token: str = ""
    bot_username: str = ""
    webhook_secret: str = ""
    api_base_url: str = "https://api.telegram.org"
    # True — idle-таска `customer_auth_tg_poll` тянет getUpdates вместо webhook:
    # хост без входящего доступа от api.telegram.org (webhook мёртв в обе стороны).
    polling_enabled: bool = False


class CustomerAuthMaxBotConfig(BaseModel):
    """Платформенный MAX-бот приёма контактов на бренд."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    access_token: str = ""
    bot_name: str = ""
    webhook_secret: str = ""
    api_base_url: str = "https://botapi.max.ru"


class CustomerAuthOAuthClientConfig(BaseModel):
    """OAuth-клиент платформы у identity-провайдера (Yandex/VK/Sber ID)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    # Оверрайды endpoint'ов (пусто — официальные URL провайдера).
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""


class CustomerAuthSmsruConfig(BaseModel):
    """SMS.RU — платный SMS/звонок-фолбек; расходы несёт платформа."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    api_id: str = ""
    sender: str = ""
    test_mode: bool = False
    code_channel: str = "sms"  # sms | call
    api_base_url: str = "https://sms.ru"


class CustomerAuthBrandConfig(BaseModel):
    """Набор провайдеров customer-auth на один apex-бренд."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    telegram: CustomerAuthTelegramBotConfig | None = None
    max: CustomerAuthMaxBotConfig | None = None
    yandex: CustomerAuthOAuthClientConfig | None = None
    vk: CustomerAuthOAuthClientConfig | None = None
    sber: CustomerAuthOAuthClientConfig | None = None
    smsru: CustomerAuthSmsruConfig | None = None


class CustomerAuthLimitsConfig(BaseModel):
    """Rate-лимиты customer-auth (Redis-окна)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    starts_per_phone_hour: int = 10
    starts_per_ip_hour: int = 30
    sends_per_phone_day: int = 20
    sends_per_ip_day: int = 60


class CustomerAuthConfig(BaseModel):
    """Платформенная авторизация покупателей по телефону (customers.mdc).

    Креды всех провайдеров принадлежат платформе (никакого BYOK у мерчантов).
    `brands` — по registrable apex (`platform_brands`); lookup регистронезависим.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    emulator_enabled: bool = True
    sms_fallback_enabled: bool = True
    session_ttl_seconds: int = 30 * 24 * 3600
    challenge_ttl_seconds: int = 600
    code_ttl_seconds: int = 300
    code_length: int = 6
    resend_cooldown_seconds: int = 60
    attempts_per_challenge: int = 5
    daily_budget_rub: int = 2000
    limits: CustomerAuthLimitsConfig = Field(default_factory=CustomerAuthLimitsConfig)
    method_priority: list[str] = Field(
        default_factory=lambda: [
            "telegram_contact",
            "max_contact",
            "yandex_id",
            "vk_id",
            "sber_id",
            "sms_code",
        ],
        description="Порядок методов для UI и авто-выбора",
    )
    brands: dict[str, CustomerAuthBrandConfig] = Field(default_factory=dict)

    @field_validator("brands")
    @classmethod
    def _lowercase_brand_keys(
        cls, value: dict[str, CustomerAuthBrandConfig]
    ) -> dict[str, CustomerAuthBrandConfig]:
        return {k.strip().lower(): v for k, v in value.items()}

    def brand(self, apex: str) -> CustomerAuthBrandConfig | None:
        """Конфиг провайдеров для apex бренда (`linnex.io`); None — не настроен."""
        return self.brands.get(apex.strip().lower())


class GeocodingConfig(BaseModel):
    """Геокодинг адресов платформы (Nominatim/OSM-совместимый API).

    Используется Shop для зон доставки и фильтра витрин по адресу покупателя.
    Endpoint заменяемый — в тестах подменяется эмулятором, в проде при росте
    нагрузки можно указать self-hosted Nominatim.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    user_agent: str = "linnex-platform/1.0 (https://linnex.io)"
    timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 30 * 24 * 3600


class PlatformBrandConfig(BaseModel):
    """Бренд платформы на одном registrable apex-домене (linnex.io, linnex.io, …)."""

    platform_name: str
    support_email: str
    models_product_name: str
    voice_product_name: str
    llms_display_label: str
    flows_product_label: str
    logo_path: str = "/static/core/assets/service_logos/frontend_logo.svg"
    legal: LegalConfig = Field(default_factory=LegalConfig)
    public_site: PublicSiteConfig = Field(default_factory=PublicSiteConfig)
    embed_api_subdomain: str = "api"
    embed_cdn_subdomain: str = "cdn"
    embed_script_path: str = "/lib/embed-flow-ui/flow-ui-embed-autoload.js"
    auth_apple_client_id: str | None = None
    vapid_email: str | None = None


def _default_linnex_platform_brand() -> PlatformBrandConfig:
    return PlatformBrandConfig(
        platform_name="Linnex",
        support_email="info@linnex.io",
        models_product_name="Linnex Models",
        voice_product_name="Linnex Voice",
        llms_display_label="Linnex LLMs",
        flows_product_label="Linnex Flows",
        legal=LegalConfig(
            contact_email="legal@linnex.io",
            support_email="helpme@linnex.io",
            dpo_email="dpo@linnex.io",
        ),
        auth_apple_client_id="app.linnex.io",
        vapid_email="admin@linnex.io",
    )


def default_platform_brands() -> dict[str, PlatformBrandConfig]:
    linnex_brand = _default_linnex_platform_brand()
    return {
        "linnex.io": linnex_brand.model_copy(deep=True),
        "localhost": linnex_brand.model_copy(deep=True),
        "lvh.me": linnex_brand.model_copy(deep=True),
        "agents-lab.ru": linnex_brand.model_copy(deep=True),
    }


def default_billing_resource_base_prices() -> dict[str, dict[str, float]]:
    """
    Базовый каталог цен до merge с shared storage и пер-компанией.

    Каждое значение — цена в условных рублях за одну единицу списания (что именно считается
    единицей, задаёт правило settlement: токены LLM, один вызов livekit и т.д.).
    Итоговая цена = значение × множитель тарифа компании (см. DEFAULT_TARIFF_PRICES).

    Ключи верхнего уровня — категория первого сегмента resource_name (формат category:resource).
    Внутри категории: имя ресурса или "*" для цены по умолчанию.

    - llm: модели (трейсы llm.*, flows.llm_resource.*, flows.llm.*). "*" — типично руб/токен.
    - embedding: RAG эмбеддинги (rag.embed.*).
    - rerank: реранк RAG за токен (spans rerank.{model}, resource из атрибута span; byok — 0).
    - stt / tts: секунды аудио / символы синтеза per-provider (spans stt.{provider}, tts.{provider}).
    - billing:rub — единица = 1 ₽; quantity из platform.billing.settlement_quantity_rub (OpenRouter USD×usd_to_rub_rate).
    - livekit: поминутное списание — room_minute, egress_composite_minute, egress_segmented_minute
      (см. apps/sync/services/livekit_usage_spans.py); "*" — прочие livekit:*.
    - search: внешние Search provider calls из search.provider.* spans.

    Категория tool в биллинге не используется (тулы flows бесплатны в учёте).
    Подробнее: billing.mdc § Модель.
    """
    return {
        "llm": {"*": 0.0001},
        "embedding": {"*": 0.00005},
        "rerank": {"*": 0.0000055, "byok": 0.0},
        "billing": {"rub": 1.0},
        "voice": {"session_minute": 0.01, "*": 0.0},
        "search": {
            "tinyfish": 0.005,
            "linkup": 0.005,
            "serper": 0.01,
            "tavily": 0.05,
            "*": 0.01,
        },
        "livekit": {
            "room_minute": 0.01,
            "egress_composite_minute": 0.05,
            "egress_segmented_minute": 0.02,
            "*": 0.0,
        },
        "guest": {
            "start": 0.05,
            "runtime_second": 0.001,
            "build_second": 0.002,
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


def default_billing_tariff_prices() -> dict[str, dict[str, dict[str, float]]]:
    """Базовый каталог тарифных множителей: TariffPlan → category → resource → multiplier."""
    return {plan.value: tree for plan, tree in DEFAULT_TARIFF_PRICES.items()}


class BillingConfig(BaseModel):
    """Тарификация: базовые цены из конфига + override через API system; settlement по трейсам."""

    balance_enforcement_enabled: bool = Field(
        default=True,
        description="Pre-flight: блокировать старт операций с pending_settlement при balance <= 0.",
    )
    balance_enforcement_exempt_company_ids: list[str] = Field(
        default_factory=lambda: ["system"],
        description="company_id без проверки баланса (например system и демо для локальной разработки).",
    )
    resource_base_prices: dict[str, dict[str, float]] = Field(
        default_factory=default_billing_resource_base_prices,
        description="Дерево category → resource → цена в руб./единицу списания; merge с storage override.",
    )
    tariff_prices: dict[str, dict[str, dict[str, float]]] = Field(
        default_factory=default_billing_tariff_prices,
        description=(
            "TariffPlan (str-значение) → category → resource → множитель. "
            "Перебивает дефолт из DEFAULT_TARIFF_PRICES; должен быть явно задан в проде "
            "(прайс одной компании ≠ прайс другой)."
        ),
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
    default_language: str | None = Field(
        default=None,
        description=(
            "Язык по умолчанию для STT (None — из `settings.voice.stt.default_language`)."
        ),
    )
    batch_download_timeout_s: float = Field(
        default=120.0,
        gt=0.0,
        description="Таймаут HTTP при скачивании файла для Sync batch STT (сек).",
    )
    chunk_max_upload_bytes: int = Field(
        default=24 * 1024 * 1024,
        ge=1024,
        description="Максимальный размер одного MP3-чанка для POST к STT.",
    )
    chunk_duration_seconds: int = Field(
        default=300,
        ge=1,
        description="Целевая длительность сегмента ffmpeg segment (сек).",
    )
    chunk_bitrate_kbps: int = Field(default=32, ge=1)
    chunk_sample_rate_hz: int = Field(default=16000, ge=1)
    chunk_channels: int = Field(default=1, ge=1)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
