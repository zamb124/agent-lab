"""
Модели ресурсов агента.

Resource = переиспользуемый компонент доступный нодам агента.
Поддерживает inline определение и ссылку на shared ресурс из БД.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.clients.llm.config import (
    LLMCallConfig,
    ReasoningEffort,
    validate_fallback_model_configs,
)
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
    endpoint_url: str | None = Field(default=None, description="S3 endpoint URL (для MinIO)")
    access_key_id: str | None = Field(default=None, description="S3 access key")
    secret_access_key: str | None = Field(default=None, description="S3 secret key")
    region: str = Field(default="us-east-1", description="S3 region")


class LLMResourceConfig(LLMCallConfig):
    """LLM модель как ресурс."""

    fallback_models: list[LLMCallConfig] | None = Field(
        default=None,
        description="Ordered список полноценных LLM-конфигов fallback-попыток.",
    )
    temperature: float | None = Field(default=0.7)

    @field_validator("fallback_models")
    @classmethod
    def _fallback_models_require_model(
        cls,
        v: list[LLMCallConfig] | None,
    ) -> list[LLMCallConfig] | None:
        return validate_fallback_model_configs(v)

    @model_validator(mode="after")
    def _provider_and_model_required(self) -> Self:
        if self.provider is None:
            raise ValueError("LLMResourceConfig.provider обязателен")
        if self.model is None:
            raise ValueError("LLMResourceConfig.model обязателен")
        return self

    def required_identity(self) -> tuple[str, str]:
        if self.provider is None or self.model is None:
            raise ValueError("LLMResourceConfig.provider/model обязательны")
        return self.provider, self.model


class LLMResourcePatch(StrictBaseModel):
    """
    Типизированный patch к LLMResourceConfig (ResourceReference.config для shared LLM).
    Все поля опциональны; неизвестные ключи в JSON запрещены (extra=forbid).
    """

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)
    fallback_models: list[LLMCallConfig] | None = Field(default=None)
    temperature: float | None = Field(default=None)
    max_tokens: int | None = Field(default=None)
    top_p: float | None = Field(default=None)
    top_k: int | None = Field(default=None)
    frequency_penalty: float | None = Field(default=None)
    presence_penalty: float | None = Field(default=None)
    seed: int | None = Field(default=None)
    reasoning_effort: ReasoningEffort | None = Field(default=None)
    api_key: str | None = Field(default=None)
    folder_id: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    extra_request_body: dict[str, Any] | None = Field(default=None)
    extra_request_headers: dict[str, str] | None = Field(default=None)

    @field_validator("fallback_models")
    @classmethod
    def _fallback_models_require_model(
        cls,
        v: list[LLMCallConfig] | None,
    ) -> list[LLMCallConfig] | None:
        return validate_fallback_model_configs(v)

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



ResourceConfigUnion = CodeResourceConfig | FilesResourceConfig | LLMResourceConfig


class ResourceDefinition(StrictBaseModel):
    """
    Полное определение ресурса.

    Используется для:
    - Хранения shared ресурсов в БД
    - Inline определения в FlowConfig
    """

    resource_id: str = Field(..., description="Уникальный ID ресурса")
    type: ResourceType = Field(..., description="Тип ресурса")
    name: str | None = Field(default=None, description="Название для отображения")
    description: str | None = Field(default=None, description="Описание ресурса")
    config: dict[str, Any] = Field(..., description="Конфигурация ресурса")
    tags: list[str] = Field(default_factory=list, description="Теги для группировки")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом. Пустой список = доступ для всех",
    )
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    def get_typed_config(self) -> CodeResourceConfig | FilesResourceConfig | LLMResourceConfig:
        """Возвращает типизированный конфиг."""
        return parse_typed_resource_config(self.type, self.config)


def parse_typed_resource_config(
    resource_type: ResourceType,
    config: dict[str, Any],
) -> ResourceConfigUnion:
    """Строгая материализация config по ResourceType (канон для резолвера и провайдеров)."""
    if resource_type == ResourceType.CODE:
        return CodeResourceConfig.model_validate(config)
    if resource_type == ResourceType.FILES:
        return FilesResourceConfig.model_validate(config)
    if resource_type == ResourceType.LLM:
        return LLMResourceConfig.model_validate(config)
    raise ValueError(f"Unknown resource type: {resource_type!r}")


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

    type: ResourceType | None = Field(default=None, description="Тип ресурса (для inline)")
    resource_id: str | None = Field(default=None, description="ID shared ресурса из БД")
    config: dict[str, Any] | None = Field(default=None, description="Конфигурация или override")
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)

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
