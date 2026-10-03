"""Каталог AI-моделей."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from pydantic import BaseModel, Field, model_validator

from core.ai.models.contracts import (
    AIAvailabilityStatus,
    AICostOrigin,
    AIModelMetadataStatus,
    ArtificialAnalysisIndices,
)
from core.ai.providers import AICapability
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class AIModelRecord(PlatformModel):
    """Модель провайдера. Глобальная таблица ``ai_models`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    ai_model_id: str = DbField(default="", db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "ai_models"
        unique_together: list[tuple[str, str]] = [("provider", "model_id")]

    provider: str = DbField(db_index=True)
    model_id: str = DbField(db_index=True)
    capabilities: tuple[AICapability, ...] = DbField(default_factory=tuple, db_type="JSONB")
    input_modalities: tuple[str, ...] = DbField(default_factory=tuple, db_type="JSONB")
    output_modalities: tuple[str, ...] = DbField(default_factory=tuple, db_type="JSONB")
    supported_parameters: tuple[str, ...] = DbField(default_factory=tuple, db_type="JSONB")
    context_length: int | None = None
    created: int | None = None
    native_dimension: int | None = None
    storage_dimension: int | None = None
    mrl_output_dimension: int | None = None
    supports_tools: bool = False
    supports_structured_output: bool = False
    is_free: bool | None = None
    free_reason: str | None = None
    free_policy: str | None = None
    pricing: JsonObject | None = DbField(default=None, db_type="JSONB")
    artificial_analysis: ArtificialAnalysisIndices | None = DbField(default=None, db_type="JSONB")
    availability_status: AIAvailabilityStatus = "unknown"
    metadata_status: AIModelMetadataStatus = "discovered"
    last_seen_at: datetime | None = None
    raw: JsonObject = DbField(default_factory=dict, db_type="JSONB")

    @model_validator(mode="after")
    def bind_ai_model_id(self) -> "AIModelRecord":
        if self.provider == "" or self.model_id == "":
            raise ValueError("provider and model_id are required")
        self.ai_model_id = f"{self.provider}:{self.model_id}"
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.provider == "" or self.model_id == "":
            raise ValueError("provider and model_id are required")
        self.ai_model_id = f"{self.provider}:{self.model_id}"

    @property
    def supports_json_schema(self) -> bool:
        return self.supports_structured_output

    @property
    def supports_vision(self) -> bool:
        return "image" in self.input_modalities

    @property
    def supports_image_output(self) -> bool:
        return "image" in self.output_modalities

    @classmethod
    async def list_by_provider(cls, provider: str) -> list[Self]:
        return await cls.objects.filter(provider=provider).all()

    @classmethod
    async def list_by_provider_capability(
        cls,
        provider: str,
        capability: AICapability,
    ) -> list[Self]:
        rows = await cls.list_by_provider(provider)
        return [row for row in rows if capability in row.capabilities]

    @classmethod
    async def get_provider_model(cls, provider: str, model_id: str) -> Self | None:
        return await cls.get(f"{provider}:{model_id}")

    @classmethod
    async def delete_by_provider(cls, provider: str) -> int:
        return await cls.objects.filter(provider=provider).delete()


class ResolvedAIModel(BaseModel):
    capability: AICapability
    provider: str | None
    model: str | None = None
    base_url: str | None = None
    endpoint_url: str | None = None
    api_key: str | None = None
    folder_id: str | None = None
    headers: JsonObject = Field(default_factory=dict)
    body: JsonObject = Field(default_factory=dict)
    dimension: int | None = None
    mrl_output_dimension: int | None = None
    cost_origin: AICostOrigin = "platform"
    fallback_models: tuple[JsonObject, ...] = Field(default_factory=tuple)
    model_record: AIModelRecord | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @property
    def billing_resource_name(self) -> str:
        if self.cost_origin == "company":
            if self.capability == AICapability.EMBEDDING:
                return "embedding:byok"
            if self.capability == AICapability.RERANK:
                return "rerank:byok"
            return "llm:byok"
        if self.capability == AICapability.EMBEDDING:
            return f"embedding:{self.model or 'embedding'}"
        if self.capability == AICapability.RERANK:
            resource = self.metadata.get("billing_resource_id")
            if isinstance(resource, str) and resource.strip():
                return f"rerank:{resource.strip()}"
            return f"rerank:{self.model or 'rerank'}"
        return f"llm:{self.model or 'unknown'}"

