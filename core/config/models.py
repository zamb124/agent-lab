"""
Модели конфигурации для различных компонентов системы.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class AuthProviderConfig(BaseModel):
    """Конфигурация провайдера авторизации"""

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scope: str = "openid profile email"
    enabled: bool = True


class AuthConfig(BaseModel):
    """Конфигурация системы авторизации"""

    enabled: bool = True
    secret_key: Optional[str] = None
    jwt_secret_key: Optional[str] = None
    session_timeout: int = 3600
    providers: Dict[str, AuthProviderConfig] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    """Конфигурация базы данных"""

    url: str = (
        "postgresql+asyncpg://agent_user:agent_password@localhost:5432/agent_platform"
    )
    checkpointer_url: str = (
        "postgresql://agent_user:agent_password@localhost:5432/agent_platform"
    )
    shared_url: Optional[str] = None  # URL для shared БД (users, companies, files)
    agents_db_url: Optional[str] = None  # URL для agents БД (agents, flows, tools)


class OpenRouterConfig(BaseModel):
    """Конфигурация OpenRouter"""

    api_key: Optional[str] = None
    base_url: str = "https://openrouter.ai/api/v1"
    site_url: str = "https://agents-lab.ru"
    site_name: str = "Agent Lab"
    timeout: int = 60
    max_retries: int = 3
    enabled: bool = True


class ModelConfig(BaseModel):
    """Конфигурация отдельной модели"""

    max_tokens: Optional[int] = None
    context_window: Optional[int] = None
    temperature: float = 0.2
    description: Optional[str] = None
    input_cost_per_token: float = 0.00001
    output_cost_per_token: float = 0.00001


class LLMConfig(BaseModel):
    """Конфигурация LLM через OpenRouter"""

    openrouter: Optional[OpenRouterConfig] = None
    models: Dict[str, ModelConfig] = Field(default_factory=dict)
    default_model: str = "x-ai/grok-code-fast-1"
    default_summarization_model: str = "google/gemini-2.5-flash"


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

    env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    domain: str = "agents-lab.ru"
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


class S3BucketConfig(BaseModel):
    """Конфигурация одного S3 бакета"""

    provider: str = "aws"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    region_name: str = "us-east-1"
    endpoint_url: Optional[str] = None
    enabled: bool = True


class S3Config(BaseModel):
    """Конфигурация S3 хранилищ"""

    enabled: bool = False
    default_bucket: Optional[str] = None
    buckets: Dict[str, S3BucketConfig] = Field(default_factory=dict)


class FashnConfig(BaseModel):
    """Конфигурация FASHN API"""

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: str = "https://api.fashn.ai/v1"
    timeout: int = 120
    poll_interval: float = 5.0
    poll_timeout: int = 600


class CloudVoiceConfig(BaseModel):
    """Конфигурация Cloud Voice API"""

    enabled: bool = False
    secret_key: Optional[str] = None
    client_id: Optional[str] = None
    auth_url: str = "https://mcs.mail.ru/auth/oauth/v1/token"
    asr_url: str = "https://voice.mcs.mail.ru/asr"
    tts_url: str = "https://voice.mcs.mail.ru/tts"
    timeout: int = 30


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
    """Конфигурация прокси для внешних запросов"""

    enabled: bool = False
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def get_proxy_url(self, protocol: str = "http") -> Optional[str]:
        """Возвращает URL прокси с авторизацией"""
        if not self.enabled:
            return None

        proxy_url = self.https_proxy if protocol == "https" else self.http_proxy
        if not proxy_url:
            return None

        if self.username and self.password:
            if "://" in proxy_url:
                protocol_part, rest = proxy_url.split("://", 1)
                return f"{protocol_part}://{self.username}:{self.password}@{rest}"
            else:
                return f"http://{self.username}:{self.password}@{proxy_url}"

        return proxy_url

    def get_proxies_dict(self) -> Optional[Dict[str, str]]:
        """Возвращает словарь прокси для httpx/requests"""
        if not self.enabled:
            return None

        proxies = {}

        http_url = self.get_proxy_url("http")
        if http_url:
            proxies["http://"] = http_url

        https_url = self.get_proxy_url("https")
        if https_url:
            proxies["https://"] = https_url

        return proxies if proxies else None


class PaymentProvidersConfig(BaseModel):
    """Конфигурация платежных провайдеров"""

    default_provider: Optional[str] = None
    providers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Платежные провайдеры (yoomoney_main, yukassa_main, etc.)"
    )


class MigrationSettings(BaseModel):
    """Настройки миграции для новых компаний"""

    default_flows: list[str] = Field(default_factory=list)
    default_agents: list[str] = Field(default_factory=list)
    default_tools: list[str] = Field(default_factory=list)
    migrate_dependencies: bool = True


class RAGProviderConfig(BaseModel):
    """Конфигурация одного RAG провайдера"""

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 60
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: Optional[str] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RAGConfig(BaseModel):
    """Конфигурация RAG системы"""

    enabled: bool = False
    default_provider: str = "agentset"
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


class OtelConfig(BaseModel):
    """Конфигурация OpenTelemetry трейсинга"""

    enabled: bool = True
    service_name: str = "agent-lab"
    instrument_langchain: bool = True
    instrument_openai: bool = True
    instrument_asyncpg: bool = True
    log_level: str = "INFO"


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
