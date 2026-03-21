"""
Конфигурация для Agents Service.

Расширяет BaseSettings добавляя специфичные для Agents поля.
"""

from typing import Optional, Dict, List
from pydantic import BaseModel, Field

from core.config import BaseSettings
from core.config.loader import load_merged_config
from core.config.models import LLMConfig, S3Config


class ExternalAgentConfig(BaseModel):
    """Конфигурация внешнего агента для инициализации"""

    url: str = Field(..., description="Base URL агента")
    auth_headers: Dict[str, str] = Field(default_factory=dict, description="Заголовки авторизации")
    name: Optional[str] = Field(
        default=None, description="Название агента (если не указано, извлекается из agent-card)"
    )


class ExternalAgentsConfig(BaseModel):
    """Конфигурация реестра внешних агентов"""

    agents: List[ExternalAgentConfig] = Field(
        default_factory=list, description="Список агентов для инициализации"
    )
    health_check_interval: int = Field(
        default=60, description="Интервал проверки здоровья в секундах"
    )


class FilesConfig(BaseModel):
    """Конфигурация для хранения файлов"""

    temp_dir: str = Field(default="tmp", description="Директория для временных файлов")


class PushConfig(BaseModel):
    """Конфигурация Web Push уведомлений"""

    enabled: bool = Field(default=True, description="Включить push уведомления")
    vapid_public_key: str = Field(
        default="BJBAqLwOEE7A7gIDCXW7vzmEwh23-ug6-1qpiuotzwROEDX_ZiVUk2BO3_eINDqXxBvxG2uRfukXVVBse167BAM",
        description="VAPID публичный ключ (URL-safe Base64)"
    )
    vapid_private_key: str = Field(
        default="n6oh3YpjV9APhmtdZ-p18P4YGLtBRLATLbprkXWAldA",
        description="VAPID приватный ключ (URL-safe Base64)"
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
    agents: dict = Field(
        default_factory=dict, description="Mock ответы для agents по ID"
    )
    nodes: dict = Field(
        default_factory=dict, description="Mock данные для nodes по ID"
    )


class AgentSettings(BaseSettings):
    """
    Настройки Agents сервиса.
    
    Наследуется от BaseSettings, добавляя специфичные для Agents поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """
    
    service_name: str = Field(default="agents", description="Имя сервиса")
    
    # Сервисные конфиги
    llm: LLMConfig = Field(default_factory=LLMConfig)
    s3: S3Config = Field(default_factory=S3Config)
    external_agents: ExternalAgentsConfig = Field(default_factory=ExternalAgentsConfig)
    files: FilesConfig = Field(default_factory=FilesConfig)
    mock: MockConfig = Field(default_factory=MockConfig)
    push: PushConfig = Field(default_factory=PushConfig)


_settings: Optional[AgentSettings] = None


def get_settings() -> AgentSettings:
    """
    Получает настройки Agents сервиса.
    
    Создает AgentSettings из конфигурации, загружая базовые настройки
    и добавляя специфичные для Agents.
    """
    global _settings
    if _settings is None:
        from core.config import set_settings as core_set_settings
        
        merged_config = load_merged_config(service_name="agents")
        _settings = AgentSettings(**merged_config)
        core_set_settings(_settings)
    
    return _settings


def set_settings(new_settings: AgentSettings) -> None:
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


