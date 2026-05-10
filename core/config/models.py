"""
Модели конфигурации для различных компонентов системы.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Self
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
        description="Внутренний или dev URL сервиса flows (ServiceClient, локальные вызовы).",
    )
    flows_webhook_public_base_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("flows_webhook_public_base_url"),
        description=(
            "Явный публичный origin без завершающего слэша для setWebhook (если отличается от "
            "канона ingress). Если пусто — {platform_public_base_url}/flows, иначе flows_service_url."
        ),
    )
    crm_service_url: Optional[str] = None
    frontend_service_url: Optional[str] = None
    rag_service_url: Optional[str] = None
    sync_service_url: Optional[str] = None
    scheduler_service_url: Optional[str] = None
    office_service_url: Optional[str] = None
    browser_service_url: Optional[str] = None
    provider_litserve_service_url: Optional[str] = None
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
    """Конфигурация cloud.ru STT (Whisper API).

    Лимиты ffmpeg-чанков для batch-транскрипции задаются в
    `MediaTranscriberConfig`, не здесь.
    """

    enabled: bool = False
    api_key: Optional[str] = None
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
# (override -> company -> deployment-default).
# ---------------------------------------------------------------------------


class LitserveSpeechBackendConfig(BaseModel):
    """HTTP-настройки backend `provider-litserve` для STT/TTS/VAD."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str = Field(
        default="http://provider-litserve:8014",
        description=(
            "Базовый URL provider-litserve (без trailing slash). "
            "Используется для /v1/audio/transcriptions, /v1/audio/speech, /v1/audio/vad."
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

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: str = "https://foundation-models.api.cloud.ru/v1/audio/speech"
    model: str = "openai/tts-1"
    voice: str = "alloy"
    response_format: Literal["wav", "mp3", "ogg", "pcm"] = "mp3"
    sample_rate: int = Field(default=24000, gt=0)
    timeout_s: float = Field(default=120.0, gt=0.0)


class YandexSTTBackendConfig(BaseModel):
    """Yandex SpeechKit STT (REST). Stub до получения ключей."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: Optional[str] = None
    folder_id: Optional[str] = None
    base_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    model: str = "general"
    timeout_s: float = Field(default=120.0, gt=0.0)


class YandexTTSBackendConfig(BaseModel):
    """Yandex SpeechKit TTS (REST). Stub до получения ключей."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    api_key: Optional[str] = None
    folder_id: Optional[str] = None
    base_url: str = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    voice: str = "ermil"
    response_format: Literal["wav", "mp3", "ogg", "pcm", "lpcm"] = "lpcm"
    sample_rate: int = Field(default=48000, gt=0)
    timeout_s: float = Field(default=60.0, gt=0.0)


class SberSTTBackendConfig(BaseModel):
    """Sber SmartSpeech STT (REST). Stub до получения ключей."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    base_url: str = "https://smartspeech.sber.ru/rest/v1/speech:recognize"
    scope: str = "SALUTE_SPEECH_PERS"
    model: str = "general"
    timeout_s: float = Field(default=120.0, gt=0.0)


class SberTTSBackendConfig(BaseModel):
    """Sber SmartSpeech TTS (REST). Stub до получения ключей."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    base_url: str = "https://smartspeech.sber.ru/rest/v1/text:synthesize"
    scope: str = "SALUTE_SPEECH_PERS"
    voice: str = "May_24000"
    response_format: Literal["wav", "mp3", "ogg", "pcm"] = "wav"
    sample_rate: int = Field(default=24000, gt=0)
    timeout_s: float = Field(default=60.0, gt=0.0)


class LocalSileroVADBackendConfig(BaseModel):
    """Локальный Silero VAD (in-process, без HTTP к provider-litserve)."""

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

    provider: Literal["litserve", "cloud_ru", "yandex", "sber", "mock"] = "litserve"
    default_model: Optional[str] = Field(
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
    litserve: LitserveSpeechBackendConfig = Field(
        default_factory=LitserveSpeechBackendConfig
    )
    cloud_ru: CloudRuSTTConfig = Field(default_factory=CloudRuSTTConfig)
    yandex: YandexSTTBackendConfig = Field(default_factory=YandexSTTBackendConfig)
    sber: SberSTTBackendConfig = Field(default_factory=SberSTTBackendConfig)


class TTSProvidersConfig(BaseModel):
    """Унифицированный конфиг TTS для voice/flows/eval."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["litserve", "cloud_ru", "yandex", "sber", "mock"] = "litserve"
    default_model: Optional[str] = Field(
        default=None,
        description="OpenAI-совместимый id модели по умолчанию (например `silero-tts-v5-5-ru`).",
    )
    default_voice: Optional[str] = None
    default_response_format: Literal["wav", "mp3", "ogg", "pcm"] = "wav"
    default_sample_rate: int = Field(default=24000, gt=0)
    chunk_max_chars: int = Field(default=100, ge=1)
    lookahead_tokens: int = Field(default=20, ge=0)
    litserve: LitserveSpeechBackendConfig = Field(
        default_factory=LitserveSpeechBackendConfig
    )
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

    model_config = ConfigDict(extra="forbid")

    provider: Literal["litserve", "silero_local", "mock"] = "silero_local"
    default_model: Optional[str] = None
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

    litserve: LitserveSpeechBackendConfig = Field(
        default_factory=LitserveSpeechBackendConfig
    )
    silero_local: LocalSileroVADBackendConfig = Field(
        default_factory=LocalSileroVADBackendConfig
    )


class VoiceDiagnosticsConfig(BaseModel):
    """Dev-only диагностика voice gateway.

    По умолчанию выключено: без явного пути в `uplink_dump_dir` ws_receiver
    не сохраняет аудио. Включать только в dev / staging для разбора жалоб
    «STT неверно распознал мои слова» — записывается тот же PCM, который
    уходит в STT-провайдер, после resampling и FIR-фильтра.
    """

    model_config = ConfigDict(extra="forbid")

    uplink_dump_dir: Optional[str] = Field(
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
        description=(
            "Жёсткий лимит размера одного дампа (MB); записи поверх лимита "
            "обрезаются."
        ),
    )


class SpeechProvidersConfig(BaseModel):
    """Единый конфиг провайдеров речи (STT/TTS/VAD).

    Доступен в любом сервисе через `get_settings().voice` — это
    deployment-default. Конкретный клиент достаётся через
    `core.clients.voice_resolver.get_stt_client / get_tts_client /
    get_vad_client(*, company_id, override)`.
    """

    model_config = ConfigDict(extra="forbid")

    stt: STTProvidersConfig = Field(default_factory=STTProvidersConfig)
    tts: TTSProvidersConfig = Field(default_factory=TTSProvidersConfig)
    vad: VADProvidersConfig = Field(default_factory=VADProvidersConfig)
    diagnostics: VoiceDiagnosticsConfig = Field(default_factory=VoiceDiagnosticsConfig)


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

    model: str = "qwen/qwen3-embedding-0.6b"
    dimension: int = 1024
    # Явный override корня ``…/v1``: при ``provider=openrouter`` пусто — из ``llm``;
    # при ``provider=provider_litserve`` пусто — из ``provider_litserve.api.base_url`` в настройках.
    base_url: Optional[str] = None
    mrl_output_dimension: Optional[int] = Field(
        default=None,
        gt=0,
        description="MRL-усечение: если задано, вектор обрезается до первых N измерений "
                    "и L2-нормализуется перед сохранением. Совпадение с dimension — плотный вектор без паддинга.",
    )


class EmbeddingConfig(BaseModel):
    """Конфигурация embedding: ``provider`` и вложенный блок ``api`` (``model``, ``dimension``, опционально ``base_url``)."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openrouter", "provider_litserve"] = "provider_litserve"
    api: EmbeddingApiConfig = Field(default_factory=EmbeddingApiConfig)

    @model_validator(mode="before")
    @classmethod
    def _lift_flat_api_fields_into_api(cls, data: Any) -> Any:
        """Плоские ``model`` / ``dimension`` / ``base_url`` на уровне ``embedding`` -> ``api`` (обратная совместимость с merge JSON)."""
        if not isinstance(data, dict):
            return data
        api: Dict[str, Any] = dict(data.get("api") or {})
        for k in ("model", "dimension", "base_url", "mrl_output_dimension"):
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

    provider: Literal["none", "provider_litserve"] = "provider_litserve"
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


class ProviderLitserveSTTModelEntry(BaseModel):
    """Описание одной STT-модели провайдера (api id ↔ HF id + параметры весов)."""

    model_config = ConfigDict(extra="forbid")

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


SILERO_TTS_RU_V5_BUNDLES: frozenset[str] = frozenset(
    ("v5_ru", "v5_2_ru", "v5_3_ru", "v5_4_ru", "v5_5_ru")
)

SILERO_V5_RU_SPEAKERS_BY_BUNDLE: dict[str, frozenset[str]] = {
    "v5_ru": frozenset(("aidar", "baya", "kseniya", "xenia", "eugene")),
    "v5_2_ru": frozenset(("aidar", "baya", "kseniya", "xenia", "eugene")),
    "v5_3_ru": frozenset(("aidar", "baya", "kseniya", "xenia", "eugene")),
    "v5_4_ru": frozenset(("aidar", "baya", "kseniya", "xenia")),
    "v5_5_ru": frozenset(("aidar", "baya", "kseniya", "xenia", "eugene")),
}


class ProviderLitserveTTSModelEntry(BaseModel):
    """Описание одной TTS-модели (api id ↔ HF id + параметры синтеза по умолчанию)."""

    model_config = ConfigDict(extra="forbid")

    api_model_id: str
    hf_model_id: str
    revision: str | None = None
    backend: Literal["silero"] = Field(
        default="silero",
        description="Runtime-адаптер TTS (silero: silero_tts + apply_tts).",
    )
    silero_language: Literal["ru"] = Field(
        default="ru",
        description="Код языка для ``silero.silero_tts`` (локальный каталог — русский v5).",
    )
    silero_bundle: str = Field(
        description=(
            "Идентификатор бандла модели Silero v5 для ``silero_tts(..., speaker=...)`` "
            "(например ``v5_5_ru``); не путать с голосом ``voice`` для ``apply_tts``."
        ),
    )
    voice: str | None = Field(
        default=None,
        description="Голос по умолчанию для ``apply_tts`` (например ``xenia``, ``aidar`` для v5_5_ru).",
    )
    synthesis_locale: str | None = Field(
        default=None,
        description=(
            "ISO 639-1 (две буквы): при совпадении с языком сессии TTS в voice_resolver "
            "(query `language` WebSocket или company_voice_providers.tts) выбирается эта запись "
            "каталога вместо tier-default."
        ),
    )
    sample_rate: int | None = Field(
        default=None,
        description="Sample rate выходного PCM (для ru v5 допустимы 8000, 24000, 48000).",
    )
    tts_input_steps: tuple[str, ...] = Field(
        default=("silero_ru_latin_to_cyrillic",),
        description=(
            "Именованные шаги подготовки текста после Unicode-нормализации на стороне LitServe. "
            "Пустой кортеж — без доп. шагов (только проверка кириллицы для silero ru). "
            "Реестр шагов — ``core.utils.tts_input_steps.TTS_INPUT_STEP_REGISTRY``."
        ),
    )

    @field_validator("voice", mode="before")
    @classmethod
    def trim_lower_voice_optional(cls, v: Any) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f"TTS voice: ожидалась str или None, получено {type(v).__name__}")
        s = v.strip().lower()
        if not s:
            return None
        return s

    @field_validator("silero_bundle", mode="before")
    @classmethod
    def normalize_silero_bundle(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError(f"TTS silero_bundle: ожидалась str, получено {type(v).__name__}")
        s = v.strip().lower()
        if not s:
            raise ValueError("TTS silero_bundle: не может быть пустым")
        if s not in SILERO_TTS_RU_V5_BUNDLES:
            allowed = ", ".join(sorted(SILERO_TTS_RU_V5_BUNDLES))
            raise ValueError(
                f"TTS silero_bundle={v!r} не из поддерживаемых русских v5: {allowed}"
            )
        return s

    @field_validator("synthesis_locale", mode="before")
    @classmethod
    def synthesis_locale_iso639(cls, v: Any) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError(f"TTS synthesis_locale: ожидалась str или None, получено {type(v).__name__}")
        s = v.strip().lower()
        if s == "":
            return None
        base = s.split("-")[0].split("_")[0]
        if len(base) < 2:
            raise ValueError("TTS synthesis_locale: нужна ISO 639-1 (минимум 2 буквы)")
        return base[:2]

    @field_validator("tts_input_steps", mode="before")
    @classmethod
    def normalize_tts_input_steps(cls, v: Any) -> tuple[str, ...]:
        if v is None:
            return ("silero_ru_latin_to_cyrillic",)
        if isinstance(v, str):
            raise ValueError("tts_input_steps: ожидался tuple или list имён шагов, не str")
        if isinstance(v, list):
            v = tuple(v)
        if not isinstance(v, tuple):
            raise ValueError(
                f"tts_input_steps: ожидался tuple или list, получено {type(v).__name__}"
            )
        out: list[str] = []
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(
                    f"tts_input_steps[{i}]: ожидалась str, получено {type(item).__name__}"
                )
            s = item.strip()
            if s == "":
                raise ValueError(f"tts_input_steps[{i}]: пустая строка")
            out.append(s)
        return tuple(out)

    @model_validator(mode="after")
    def sample_rate_must_be_v5_ru_choice(self) -> Self:
        if self.sample_rate is None:
            return self
        if self.sample_rate not in (8000, 24000, 48000):
            raise ValueError(
                f"TTS sample_rate={self.sample_rate}: для Silero ru v5 допустимы только 8000, 24000, 48000"
            )
        return self

    @model_validator(mode="after")
    def voice_must_match_silero_bundle(self) -> Self:
        if self.voice is None:
            return self
        allowed = SILERO_V5_RU_SPEAKERS_BY_BUNDLE.get(self.silero_bundle)
        if allowed is None:
            raise ValueError(f"TTS: нет таблицы голосов для silero_bundle={self.silero_bundle!r}")
        if self.voice not in allowed:
            opts = ", ".join(sorted(allowed))
            raise ValueError(
                f"TTS voice={self.voice!r} недопустим для silero_bundle={self.silero_bundle!r}; "
                f"допустимы: {opts}"
            )
        return self

    @model_validator(mode="after")
    def tts_input_steps_must_be_registered(self) -> Self:
        from core.utils.tts_input_steps import TTS_INPUT_STEP_IDS

        unknown = [s for s in self.tts_input_steps if s not in TTS_INPUT_STEP_IDS]
        if unknown:
            allowed = ", ".join(sorted(TTS_INPUT_STEP_IDS))
            raise ValueError(
                f"tts_input_steps: неизвестные шаги {unknown}; зарегистрированы: {allowed}"
            )
        return self


class ProviderLitserveVADModelEntry(BaseModel):
    """Описание одной VAD-модели (api id ↔ HF id + параметры детекции)."""

    model_config = ConfigDict(extra="forbid")

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


class ProviderLitserveInfraConfig(BaseModel):
    """
    Деплой локального OpenAI-совместимого LitServe: один HTTP-порт, воркеры эмбеддингов и реранка.

    Относится к процессу ``apps.provider_litserve.main``, не к доменному ``rag.reranker``.
    Переопределение деплоя: ``services.provider_litserve``; ENV: ``PROVIDER_LITSERVE__INFRA__*``.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_default_audio_api_model_keys(cls, data: Any) -> Any:
        """DEPRECATED ключи вида ``default_*_api_model_id`` (дубль ENV на кластере)."""
        if not isinstance(data, dict):
            return data
        for legacy, canonical in (
            ("default_stt_api_model_id", "stt_default_api_model_id"),
            ("default_tts_api_model_id", "tts_default_api_model_id"),
            ("default_vad_api_model_id", "vad_default_api_model_id"),
        ):
            if legacy not in data:
                continue
            legacy_val = data.pop(legacy)
            if canonical not in data:
                data[canonical] = legacy_val
        return data

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
            "cpu — принудительно CPU (разгрузка VRAM под STT/chat на малой карте)."
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
    model_id: str = "Qwen/Qwen3-Reranker-0.6B"

    use_fp16: bool = True
    use_bf16: bool = False
    normalize_scores: bool = True

    embedding_model_id: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_openai_model_id: str = "qwen/qwen3-embedding-0.6b"
    rerank_openai_model_id: str = "qwen/qwen3-reranker-0.6b"
    llm_model_id: str = "Qwen/Qwen2.5-1.5B-Instruct"
    embedding_model_ids: list[str] = Field(default_factory=list)
    rerank_model_ids: list[str] = Field(default_factory=list)
    llm_model_ids: list[str] = Field(
        default_factory=lambda: [
            "Qwen/Qwen2.5-1.5B-Instruct",
        ],
    )
    markdown_default_api_model_id: str = Field(
        default="Qwen/Qwen2.5-1.5B-Instruct",
        description=(
            "api/HF id LLM по умолчанию для POST /v1/text/format_markdown (должен быть в llm_model_ids или реестре). "
            "Дефолт совпадает с llm_model_id — та же локальная модель, что для чата и суммаризации через LitServe."
        ),
    )
    markdown_max_chunk_chars: int = Field(
        default=6000,
        ge=512,
        le=100_000,
        description="Максимум символов на чанк перед батчевым generate.",
    )
    markdown_max_microbatch: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Сколько чанков за один вызов model.generate (меньше — ниже пик RAM на KV-cache).",
    )
    markdown_max_new_tokens: int = Field(
        default=1024,
        ge=64,
        le=8192,
        description=(
            "Лимит новых токенов на один чанк (после промпта). Фактический вызов generate использует "
            "min(это значение, длина промпта + slack) — меньше простоя без EOS на коротких чанках."
        ),
    )
    markdown_chunk_join: str = Field(
        default="\n\n",
        description="Склейка между отформатированными чанками в одном ответе.",
    )
    markdown_tokenizer_max_length: int = Field(
        default=8192,
        ge=512,
        le=131072,
        description="truncation max_length при токенизации батча промптов.",
    )
    markdown_format_repetition_penalty: float = Field(
        default=1.15,
        ge=1.0,
        le=2.0,
        description="repetition_penalty для POST /v1/text/format_markdown (1.0 — без штрафа).",
    )
    markdown_microbatch_peak_cap: int = Field(
        default=2,
        ge=1,
        le=16,
        description=(
            "Верхняя граница эффективного microbatch для format_markdown: "
            "min(запрошенный microbatch, этот cap). Снижает пик памяти; на GPU cap можно поднять."
        ),
    )

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
            "Дефолт указывается в stt_default_api_model_id. Расширяется из UI /litserve/models."
        ),
    )
    stt_default_api_model_id: str = Field(
        default="gigaam-v3-rnnt-ru",
        description="api id STT-модели по умолчанию (должен присутствовать в stt_models).",
    )

    tts_models: list["ProviderLitserveTTSModelEntry"] = Field(
        default_factory=lambda: [
            ProviderLitserveTTSModelEntry(
                api_model_id="silero-tts-v5-5-ru",
                hf_model_id="snakers4/silero-models",
                silero_bundle="v5_5_ru",
                voice="xenia",
                synthesis_locale="ru",
                sample_rate=24000,
            ),
        ],
        description=(
            "Полный список TTS-моделей провайдера. Каждый элемент описывает одну модель "
            "(api id для /v1/audio/speech, hf id каталога, silero_bundle, voice, sample_rate). "
            "Дефолт указывается в tts_default_api_model_id. Расширяется из UI /litserve/models."
        ),
    )
    tts_default_api_model_id: str = Field(
        default="silero-tts-v5-5-ru",
        description="api id TTS-модели по умолчанию (должен присутствовать в tts_models).",
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
            "Дефолт указывается в vad_default_api_model_id. Расширяется из UI /litserve/models."
        ),
    )
    vad_default_api_model_id: str = Field(
        default="silero-vad-v5",
        description="api id VAD-модели по умолчанию (должен присутствовать в vad_models).",
    )

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
    TTL по умолчанию, параметры фоновой очистки и перевекторизации документов RAG.

    Клиент задаёт время жизни через ``ttl_seconds`` в metadata при загрузке;
    ``0`` — бессрочно. Если ключ отсутствует, применяется ``default_ttl_seconds``.
    Джобы планируются процессом ``scheduler``, исполняются в очереди ``rag``.
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
    default_retry_count: int = Field(
        default=3,
        ge=1,
        le=100,
        description=(
            "Верхняя граница повторов SimpleRetryMiddleware, когда у задачи нет метки max_retries "
            "(fallback через labels таска)."
        ),
    )


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


class YandexLLMProviderConfig(BaseModel):
    """Yandex Cloud Foundation Models (OpenAI-совместимый endpoint): Api-Key + x-folder-id."""

    api_key: Optional[str] = Field(default=None)
    folder_id: Optional[str] = Field(
        default=None,
        description="Идентификатор каталога Yandex Cloud (заголовок x-folder-id)",
    )
    base_url: str = Field(default="https://llm.api.cloud.yandex.net/v1")


class ModelConfig(BaseModel):
    """Конфигурация модели — переопределение temperature/max_tokens для конкретной модели"""

    temperature: float = Field(default=0.2)
    max_tokens: Optional[int] = Field(default=None)


class LLMConfig(BaseModel):
    """Конфигурация LLM с поддержкой нескольких провайдеров"""

    provider: str = Field(
        default="openai",
        description="Провайдер: openai, openrouter, bothub, provider_litserve, yandex",
    )
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
    yandex: Optional[YandexLLMProviderConfig] = Field(default=None)
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


class PublicSiteConfig(BaseModel):
    """Публичные настройки маркетингового слоя сайта (виджеты, аналитика, комьюнити)."""

    telegram_community_url: Optional[str] = None
    yandex_metrika_id: Optional[str] = None
    google_analytics_measurement_id: Optional[str] = None


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
