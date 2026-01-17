"""
Модели ресурсов агента.

Resource = переиспользуемый компонент доступный нодам агента.
Поддерживает inline определение и ссылку на shared ресурс из БД.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from core.models import StrictBaseModel


class ResourceType(str, Enum):
    """Типы ресурсов."""
    
    CODE = "code"           # Inline Python/JS код
    RAG = "rag"             # RAG namespace
    FILES = "files"         # S3/MinIO файлы
    PROMPT = "prompt"       # Шаблон промпта
    LLM = "llm"             # LLM модель
    SECRET = "secret"       # Секрет (резолвится из @var:)
    HTTP = "http"           # HTTP endpoint
    CACHE = "cache"         # Redis cache namespace


class CodeLanguage(str, Enum):
    """Языки для code ресурсов."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"


# --- Конфигурации для каждого типа ресурса ---

class CodeResourceConfig(StrictBaseModel):
    """Inline код как ресурс."""
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)
    code: str = Field(..., description="Inline код с функциями/классами")


class RAGResourceConfig(StrictBaseModel):
    """RAG namespace как ресурс."""
    namespace: str = Field(..., description="ID или scope namespace")
    provider: str = Field(default="chromadb", description="RAG провайдер")
    default_top_k: int = Field(default=5, description="Дефолтное количество результатов")


class FilesResourceConfig(StrictBaseModel):
    """Файловое хранилище как ресурс."""
    bucket: str = Field(..., description="S3 bucket")
    prefix: str = Field(default="", description="Префикс пути")
    endpoint_url: Optional[str] = Field(default=None, description="S3 endpoint URL (для MinIO)")
    access_key_id: Optional[str] = Field(default=None, description="S3 access key")
    secret_access_key: Optional[str] = Field(default=None, description="S3 secret key")
    region: str = Field(default="us-east-1", description="S3 region")


class PromptResourceConfig(StrictBaseModel):
    """Шаблон промпта как ресурс."""
    template: str = Field(..., description="Jinja2 шаблон")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Дефолтные переменные")


class LLMResourceConfig(StrictBaseModel):
    """LLM модель как ресурс."""
    provider: str = Field(..., description="openrouter, openai, bothub")
    model: str = Field(..., description="Имя модели")
    temperature: float = Field(default=0.7)
    max_tokens: Optional[int] = Field(default=None)
    api_key: Optional[str] = Field(default=None, description="@var:KEY или прямой ключ")
    base_url: Optional[str] = Field(default=None, description="Base URL провайдера")


class SecretResourceConfig(StrictBaseModel):
    """Секрет как ресурс."""
    key: str = Field(..., description="@var:SECRET_NAME")


class HTTPResourceConfig(StrictBaseModel):
    """HTTP endpoint как ресурс."""
    base_url: str = Field(..., description="Base URL")
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(default=30)
    auth_type: Optional[str] = Field(default=None, description="bearer, basic, api_key")
    auth_value: Optional[str] = Field(default=None, description="Токен или @var:KEY")


class CacheResourceConfig(StrictBaseModel):
    """Redis cache namespace."""
    namespace: str = Field(..., description="Cache namespace prefix")
    ttl: int = Field(default=3600, description="TTL в секундах")


# --- Главные модели ---

class ResourceDefinition(StrictBaseModel):
    """
    Полное определение ресурса.
    
    Используется для:
    - Хранения shared ресурсов в БД
    - Inline определения в AgentConfig
    """
    
    resource_id: str = Field(..., description="Уникальный ID ресурса")
    type: ResourceType = Field(..., description="Тип ресурса")
    name: Optional[str] = Field(default=None, description="Название для отображения")
    description: Optional[str] = Field(default=None, description="Описание ресурса")
    config: Dict[str, Any] = Field(..., description="Конфигурация ресурса")
    tags: List[str] = Field(default_factory=list, description="Теги для группировки")
    permission: List[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = доступ для всех"
    )
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    
    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: Optional[Union[str, List[str]]]) -> List[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v
    
    def get_typed_config(self) -> Union[
        CodeResourceConfig,
        RAGResourceConfig,
        FilesResourceConfig,
        PromptResourceConfig,
        LLMResourceConfig,
        SecretResourceConfig,
        HTTPResourceConfig,
        CacheResourceConfig,
    ]:
        """Возвращает типизированный конфиг."""
        config_map = {
            ResourceType.CODE: CodeResourceConfig,
            ResourceType.RAG: RAGResourceConfig,
            ResourceType.FILES: FilesResourceConfig,
            ResourceType.PROMPT: PromptResourceConfig,
            ResourceType.LLM: LLMResourceConfig,
            ResourceType.SECRET: SecretResourceConfig,
            ResourceType.HTTP: HTTPResourceConfig,
            ResourceType.CACHE: CacheResourceConfig,
        }
        config_class = config_map[self.type]
        return config_class.model_validate(self.config)


class ResourceReference(BaseModel):
    """
    Ссылка на ресурс в AgentConfig/NodeConfig.
    
    Может быть:
    1. Inline - type + config (полное определение)
    2. Reference - resource_id (ссылка на shared ресурс из БД)
    3. Reference с override - resource_id + config (ссылка + переопределение)
    
    Примеры:
    - Inline: {"type": "code", "config": {"language": "python", "code": "..."}}
    - Reference: {"resource_id": "company_docs"}
    - Override: {"resource_id": "gpt4", "config": {"temperature": 0.3}}
    """
    
    # Для inline
    type: Optional[ResourceType] = Field(default=None, description="Тип ресурса (для inline)")
    
    # Для reference на shared
    resource_id: Optional[str] = Field(default=None, description="ID shared ресурса из БД")
    
    # Конфигурация (для inline - полная, для reference - override)
    config: Optional[Dict[str, Any]] = Field(default=None, description="Конфигурация или override")
    
    # Метаданные (опционально для inline)
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    
    @model_validator(mode="after")
    def validate_reference_or_inline(self) -> "ResourceReference":
        """Проверяет что указан либо type (inline), либо resource_id (reference)."""
        if self.type is None and self.resource_id is None:
            raise ValueError("ResourceReference must have either 'type' (inline) or 'resource_id' (reference)")
        if self.type is not None and self.resource_id is not None:
            raise ValueError("ResourceReference cannot have both 'type' and 'resource_id'")
        if self.type is not None and self.config is None:
            raise ValueError("Inline ResourceReference must have 'config'")
        return self
    
    @property
    def is_inline(self) -> bool:
        """True если это inline ресурс."""
        return self.type is not None
    
    @property
    def is_reference(self) -> bool:
        """True если это ссылка на shared ресурс."""
        return self.resource_id is not None


__all__ = [
    "ResourceType",
    "CodeLanguage",
    "CodeResourceConfig",
    "RAGResourceConfig",
    "FilesResourceConfig",
    "PromptResourceConfig",
    "LLMResourceConfig",
    "SecretResourceConfig",
    "HTTPResourceConfig",
    "CacheResourceConfig",
    "ResourceDefinition",
    "ResourceReference",
]
