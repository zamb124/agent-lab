"""
Модели ресурсов агента.

Resource = переиспользуемый компонент доступный нодам агента.
Поддерживает inline определение и ссылку на shared ресурс из БД.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal, Self, TypeAlias, assert_never, override

from oxyde import Field as DbField
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.flows.src.models.rag_resource_bind import RagResourceBindParams
from core.ai.llm_config import (
    LLMCallConfig,
    ReasoningEffort,
    validate_fallback_model_configs,
)
from core.context.context import get_context
from core.llm_context.models import LLMContextPatch
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject, JsonValue, require_json_object


class ResourceType(str, Enum):
    """Типы ресурсов."""

    LLM = "llm"
    LLM_CONTEXT = "llm_context"
    HANDOFF_CONTEXT = "handoff_context"
    RAG = "rag"
    FILES = "files"
    DATA_TABLE = "data_table"


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
            raise ValueError("LLMResourceConfig.provider is required")
        if self.model is None:
            raise ValueError("LLMResourceConfig.model is required")
        return self

    def required_identity(self) -> tuple[str, str]:
        if self.provider is None or self.model is None:
            raise ValueError("LLMResourceConfig.provider/model are required")
        return self.provider, self.model


class LLMResourcePatch(StrictBaseModel):
    """
    Типизированный patch к LLMResourceConfig (ResourceReference.config для shared LLM).
    Все поля опциональны; неизвестные ключи в JSON запрещены (extra=forbid).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

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
    extra_request_body: JsonObject | None = Field(default=None)
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
    def _extra_body_must_be_object(cls, value: JsonValue) -> JsonObject | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return require_json_object(value, "extra_request_body")
        raise ValueError("extra_request_body must be a JSON object, not an array or scalar")

    @field_validator("extra_request_headers", mode="before")
    @classmethod
    def _extra_headers_must_be_object(cls, value: JsonValue) -> dict[str, str] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("extra_request_headers must be a JSON object, not an array or scalar")
        headers: dict[str, str] = {}
        for key, val in value.items():
            if not key.strip():
                raise ValueError("extra_request_headers: keys must be non-empty strings")
            if not isinstance(val, str):
                raise ValueError("extra_request_headers: values must be strings")
            headers[key] = val
        return headers



class DataTableResourceConfig(StrictBaseModel):
    """SQLite DataTable file bound to a flow (public id = file_id)."""

    file_id: str = Field(default="", description="Platform FileRecord.file_id")


ResourceConfigUnion: TypeAlias = (
    LLMResourceConfig | LLMContextPatch | RagResourceBindParams | DataTableResourceConfig | JsonObject
)


class ResourceDefinition(CompanyScopedModel):
    """Shared-ресурс компании. Таблица ``resources`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"

    class Meta:
        is_table: bool = True
        table_name: str = "resources"
        unique_together: list[tuple[str, str]] = [("company_id", "resource_id")]

    resource_id: str = DbField(min_length=1, db_index=True, description="Уникальный ID ресурса")
    type: ResourceType = DbField(description="Тип ресурса")
    config: JsonObject = DbField(db_type="JSONB", description="Конфигурация ресурса")
    company_id: str = DbField(default="", db_index=True)
    resource_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    name: str | None = DbField(default=None, description="Название для отображения")
    description: str | None = DbField(default=None, description="Описание ресурса")
    tags: list[str] = DbField(default_factory=list, description="Теги для группировки")
    permission: list[str] = DbField(
        default_factory=list,
        description="Группы с доступом. Пустой список = company-visible (member компании)",
    )
    created_at: datetime | None = DbField(default=None)
    updated_at: datetime | None = DbField(default=None)

    @field_validator("permission", mode="before")
    @classmethod
    def validate_permission(cls, v: str | list[str] | None) -> list[str]:
        """Конвертирует None в [], string в [string]."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @classmethod
    def resource_row_id_for_active_company(cls, resource_id: str) -> str:
        """Ключ company_id:resource_id из активной компании. Нет компании — ValueError. Пустой resource_id или двоеточие в resource_id либо в компании — ValueError."""
        ctx = get_context()
        if ctx is None or ctx.active_company is None or ctx.active_company.company_id == "":
            raise ValueError("resource_id requires an active company")
        if resource_id == "" or ":" in resource_id or ":" in ctx.active_company.company_id:
            raise ValueError("resource_id and company_id must not contain ':'")
        return f"{ctx.active_company.company_id}:{resource_id}"

    @model_validator(mode="after")
    def bind_company(self) -> Self:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            return self
        company_id = ctx.active_company.company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        expected = type(self).resource_row_id_for_active_company(self.resource_id)
        if self.resource_row_id == "":
            self.resource_row_id = expected
        elif self.resource_row_id != expected:
            raise ValueError("resource_row_id does not match company_id and resource_id")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        expected = type(self).resource_row_id_for_active_company(self.resource_id)
        if self.company_id == "" or self.resource_row_id != expected:
            raise ValueError("resource_row_id does not match the active company")
        now = datetime.now(timezone.utc)
        if is_create and self.created_at is None:
            self.created_at = now
        self.updated_at = now
        _ = update_fields

    def get_typed_config(self) -> ResourceConfigUnion:
        """Возвращает типизированный конфиг."""
        return parse_typed_resource_config(self.type, self.config)


class ResourceListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    type: ResourceType | None = None


class ResourceIdPayload(StrictBaseModel):
    resource_id: str = Field(min_length=1)


class ResourceUpdateRequest(StrictBaseModel):
    name: str | None = None
    description: str | None = None
    config: JsonObject | None = None
    tags: list[str] | None = None
    permission: list[str] | None = None


class ResourceUpdatePayload(ResourceUpdateRequest):
    resource_id: str = Field(min_length=1)


class ResourceDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    resource_id: str


def parse_typed_resource_config(
    resource_type: ResourceType,
    config: JsonObject,
) -> ResourceConfigUnion:
    """Строгая материализация config по ResourceType."""
    if resource_type == ResourceType.LLM:
        return LLMResourceConfig.model_validate(config)
    if resource_type == ResourceType.LLM_CONTEXT:
        return LLMContextPatch.model_validate(config)
    if resource_type == ResourceType.RAG:
        return RagResourceBindParams.model_validate(config)
    if resource_type == ResourceType.DATA_TABLE:
        return DataTableResourceConfig.model_validate(config)
    if resource_type == ResourceType.FILES:
        return dict(config)
    if resource_type == ResourceType.HANDOFF_CONTEXT:
        return dict(config)
    assert_never(resource_type)

class ResourceReference(BaseModel):
    """
    Ссылка на ресурс в FlowConfig/NodeConfig.

    Может быть:
    1. Inline - type + config (полное определение)
    2. Reference - resource_id (ссылка на shared ресурс из БД)
    3. Reference с override - resource_id + config (ссылка + переопределение)

    Примеры:
    - Inline: {"type": "llm", "config": {"provider": "openrouter", "model": "..."}}
    - Reference: {"resource_id": "company_llm"}
    - Override: {"resource_id": "gpt4", "config": {"temperature": 0.3}}
    """

    type: ResourceType | None = Field(default=None, description="Тип ресурса (для inline)")
    resource_id: str | None = Field(default=None, description="ID shared ресурса из БД")
    config: JsonObject | None = Field(default=None, description="Конфигурация или override")
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом для inline-ресурса. Пустой список = company-visible",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def validate_reference_permission(cls, v: str | list[str] | None) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

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


ResourceReferenceInput: TypeAlias = ResourceReference | JsonObject
ResourceMapInput: TypeAlias = dict[str, ResourceReferenceInput]


__all__ = [
    "ResourceType",
    "LLMResourceConfig",
    "LLMResourcePatch",
    "DataTableResourceConfig",
    "RagResourceBindParams",
    "ResourceConfigUnion",
    "parse_typed_resource_config",
    "ResourceDefinition",
    "ResourceListPayload",
    "ResourceIdPayload",
    "ResourceUpdateRequest",
    "ResourceUpdatePayload",
    "ResourceDeletedResponse",
    "ResourceReference",
    "ResourceReferenceInput",
    "ResourceMapInput",
]
