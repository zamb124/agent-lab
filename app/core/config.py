"""
Конфигурация приложения.
Поддерживает загрузку из .env и переопределение через conf.json
"""

import logging
import os
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from .config_utils import load_merged_config

logger = logging.getLogger(__name__)


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
    session_timeout: int = 3600  # секунд
    providers: Dict[str, AuthProviderConfig] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    """Конфигурация базы данных"""

    url: str = (
        "postgresql+asyncpg://agent_user:agent_password1@127.0.0.1:5433/agent_platform"
    )
    checkpointer_url: str = (
        "postgresql://agent_user:agent_password1@127.0.0.1:5433/agent_platform"
    )


class LLMProviderConfig(BaseModel):
    """Конфигурация одного LLM провайдера"""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str = "gpt-4"
    default_temperature: float = 0.2
    timeout: int = 30
    max_retries: int = 3
    enabled: bool = True
    models: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )  # Специфичные настройки для моделей


class LLMConfig(BaseModel):
    """Конфигурация всех LLM провайдеров"""

    default_provider: str = "openai"
    providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)


class ServerConfig(BaseModel):
    """Конфигурация сервера"""

    env: str = "production"  # local, production, staging
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    domain: str = "agents-lab.ru"  # Основной домен для поддоменов


class WorkerConfig(BaseModel):
    """Конфигурация воркеров"""

    max_workers: int = 4
    task_poll_interval: int = 5  # секунд


class S3BucketConfig(BaseModel):
    """Конфигурация одного S3 бакета"""

    provider: str = "aws"  # aws, yandex, minio
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    region_name: str = "us-east-1"
    endpoint_url: Optional[str] = None  # Для совместимых сервисов
    enabled: bool = True


class S3Config(BaseModel):
    """Конфигурация S3 хранилищ"""

    enabled: bool = False
    default_bucket: Optional[str] = None  # Имя дефолтного бакета
    buckets: Dict[str, S3BucketConfig] = Field(
        default_factory=dict
    )  # Конфигурации бакетов


class FashnConfig(BaseModel):
    """Конфигурация FASHN API"""

    enabled: bool = False
    api_key: Optional[str] = None
    base_url: str = "https://api.fashn.ai/v1"
    timeout: int = 120  # Увеличиваем таймаут HTTP запросов до 2 минут
    poll_interval: float = 5.0  # Увеличиваем интервал опроса до 5 секунд
    poll_timeout: int = 600  # Увеличиваем общий таймаут до 10 минут


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
    bots: Dict[str, str] = Field(default_factory=dict)  # bot_name -> token


class NanoBananaConfig(BaseModel):
    """Конфигурация Nano Banana (Gemini Image Generation)"""

    enabled: bool = False
    api_key: Optional[str] = None
    model_name: str = "gemini-2.5-flash-image-preview"
    timeout: int = 60
class AmoCRMConfig(BaseModel):
    """Конфигурация AmoCRM интеграции. Временно тут, пока не настроим OAuth"""
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

    default_flows: list[str] = Field(
        default_factory=lambda: [
            "app.flows.test_flow.test_flow_config",
            "app.flows.weather_flow.weather_flow_config",
        ],
        description="Список flow для миграции в новую компанию"
    )
    default_agents: list[str] = Field(
        default_factory=lambda: [
            "app.agents.calculator.agent.CalculatorAgent",
        ],
        description="Список агентов для миграции в новую компанию (если нужны без flow)"
    )
    default_tools: list[str] = Field(
        default_factory=lambda: [
            "app.tools.calc_tools.calculate",
            "app.tools.calc_tools.get_math_help",
        ],
        description="Список тулов для миграции в новую компанию (если нужны отдельно)"
    )
    migrate_dependencies: bool = Field(
        default=True,
        description="Мигрировать ли зависимости автоматически при миграции flow"
    )


class Settings(BaseSettings):
    """Настройки приложения с поддержкой JSON конфигурации"""

    # Подсекции конфигурации
    auth: AuthConfig = Field(default_factory=AuthConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    s3: S3Config = Field(default_factory=S3Config)
    fashn: FashnConfig = Field(default_factory=FashnConfig)
    cloud_voice: CloudVoiceConfig = Field(default_factory=CloudVoiceConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    nano_banana: NanoBananaConfig = Field(default_factory=NanoBananaConfig)
    amocrm: AmoCRMConfig = Field(default_factory=AmoCRMConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    payment_providers: PaymentProvidersConfig = Field(default_factory=PaymentProvidersConfig)
    migration: MigrationSettings = Field(default_factory=MigrationSettings)

    def __init__(self, **data):
        # Загружаем JSON конфигурацию и объединяем с переданными данными
        json_config = load_merged_config()

        # JSON имеет более низкий приоритет чем переданные данные и env переменные
        final_data = {**json_config, **data}

        super().__init__(**final_data)

    class Config:
        env_file = [
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),  # .env в корне проекта
            ".env",
        ]
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"  # Разделитель для вложенных переменных
        extra = "allow"


# Глобальный экземпляр настроек (синглтон)
_settings_instance = None


def get_settings() -> Settings:
    """Получает синглтон настроек"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


# Для обратной совместимости
settings = get_settings()
