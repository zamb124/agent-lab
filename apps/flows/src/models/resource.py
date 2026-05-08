"""
Модели ресурсов агента.

Resource = переиспользуемый компонент доступный нодам агента.
Поддерживает inline определение и ссылку на shared ресурс из БД.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.models import StrictBaseModel


class ResourceType(str, Enum):
    """Типы ресурсов."""

    CODE = "code"
    FILES = "files"
    LLM = "llm"


class CodeLanguage(str, Enum):
    """Языки для code ресурсов."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"


class CodeResourceConfig(StrictBaseModel):
    """Inline код как ресурс."""

    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)
    code: str = Field(..., description="Inline код с функциями/классами")


class FilesResourceConfig(StrictBaseModel):
    """Файловое хранилище как ресурс."""

    bucket: str = Field(..., description="S3 bucket")
    prefix: str = Field(default="", description="Префикс пути")
    endpoint_url: Optional[str] = Field(default=None, description="S3 endpoint URL (для MinIO)")
    access_key_id: Optional[str] = Field(default=None, description="S3 access key")
    secret_access_key: Optional[str] = Field(default=None, description="S3 secret key")
    region: str = Field(default="us-east-1", description="S3 region")


class LLMResourceConfig(StrictBaseModel):
    """LLM модель как ресурс."""

    provider: str = Field(..., description="openrouter, openai, bothub, provider_litserve, yandex")
    model: str = Field(..., description="Имя модели")
    temperature: float = Field(default=0.7)
    max_tokens: Optional[int] = Field(default=None)
    api_key: Optional[str] = Field(default=None, description="@var:KEY или прямой ключ")
    folder_id: Optional[str] = Field(
        default=None,
        description="Yandex Cloud folder id; с собственным api_key для yandex — если не задан глобальный llm.yandex.folder_id",
    )
    base_url: Optional[str] = Field(default=None, description="Base URL провайдера")
    extra_request_body: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Доп. поля тела POST /chat/completions; мерж последним в запросе",
    )
    extra_request_headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Доп. HTTP заголовки; мерж последним, перекрывает заголовки провайдера",
    )

    @field_validator("extra_request_body", mode="before")
    @classmethod
    def _extra_body_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        raise ValueError("extra_request_body должен быть объектом JSON, не массивом и не скаляром")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("extra_request_headers должен быть объектом JSON, не массивом и не скаляром")
        for key, val in v.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("extra_request_headers: ключи — непустые строки")
            if not isinstance(val, str):
                raise ValueError("extra_request_headers: значения должны быть строками")
        return v


class LLMResourcePatch(StrictBaseModel):
    """
    Типизированный patch к LLMResourceConfig (ResourceReference.config для shared LLM).
    Все поля опциональны; неизвестные ключи в JSON запрещены (extra=forbid).
    """

    model_config = ConfigDict(extra="forbid")

    provider: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    temperature: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None)
    api_key: Optional[str] = Field(default=None)
    folder_id: Optional[str] = Field(default=None)
    base_url: Optional[str] = Field(default=None)
    extra_request_body: Optional[Dict[str, Any]] = Field(default=None)
    extra_request_headers: Optional[Dict[str, str]] = Field(default=None)

    @field_validator("extra_request_body", mode="before")
    @classmethod
    def _extra_body_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        raise ValueError("extra_request_body должен быть объектом JSON, не массивом и не скаляром")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("extra_request_headers должен быть объектом JSON, не массивом и не скаляром")
        for key, val in v.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("extra_request_headers: ключи — непустые строки")
            if not isinstance(val, str):
                raise ValueError("extra_request_headers: значения должны быть строками")
        return v


ResourceConfigUnion = Union[
    CodeResourceConfig,
    FilesResourceConfig,
    LLMResourceConfig,
]


class ResourceDefinition(StrictBaseModel):
    """
    Полное определение ресурса.

    Используется для:
    - Хранения shared ресурсов в БД
    - Inline определения в FlowConfig
    """

    resource_id: str = Field(..., description="Уникальный ID ресурса")
    type: ResourceType = Field(..., description="Тип ресурса")
    name: Optional[str] = Field(default=None, description="Название для отображения")
    description: Optional[str] = Field(default=None, description="Описание ресурса")
    config: Dict[str, Any] = Field(..., description="Конфигурация ресурса")
    tags: List[str] = Field(default_factory=list, description="Теги для группировки")
    permission: List[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = доступ для всех",
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

    def get_typed_config(self) -> Union[CodeResourceConfig, FilesResourceConfig, LLMResourceConfig]:
        """Возвращает типизированный конфиг."""
        return parse_typed_resource_config(self.type, self.config)


_RESOURCE_CONFIG_CLASS_BY_TYPE: Dict[ResourceType, Type[StrictBaseModel]] = {
    ResourceType.CODE: CodeResourceConfig,
    ResourceType.FILES: FilesResourceConfig,
    ResourceType.LLM: LLMResourceConfig,
}


def parse_typed_resource_config(
    resource_type: ResourceType,
    config: Dict[str, Any],
) -> ResourceConfigUnion:
    """Строгая материализация config по ResourceType (канон для резолвера и провайдеров)."""
    cls = _RESOURCE_CONFIG_CLASS_BY_TYPE.get(resource_type)
    if cls is None:
        raise ValueError(f"Unknown resource type: {resource_type!r}")
    return cls.model_validate(config)  # type: ignore[return-value]


class ResourceReference(BaseModel):
    """
    Ссылка на ресурс в FlowConfig/NodeConfig.

    Может быть:
    1. Inline - type + config (полное определение)
    2. Reference - resource_id (ссылка на shared ресурс из БД)
    3. Reference с override - resource_id + config (ссылка + переопределение)

    Примеры:
    - Inline: {"type": "code", "config": {"language": "python", "code": "..."}}
    - Reference: {"resource_id": "company_docs"}
    - Override: {"resource_id": "gpt4", "config": {"temperature": 0.3}}
    """

    type: Optional[ResourceType] = Field(default=None, description="Тип ресурса (для inline)")
    resource_id: Optional[str] = Field(default=None, description="ID shared ресурса из БД")
    config: Optional[Dict[str, Any]] = Field(default=None, description="Конфигурация или override")
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
    "FilesResourceConfig",
    "LLMResourceConfig",
    "LLMResourcePatch",
    "ResourceConfigUnion",
    "parse_typed_resource_config",
    "ResourceDefinition",
    "ResourceReference",
]
