from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.ai.providers import AICapability
from core.types import JsonObject

AIAvailabilityStatus = Literal[
    "unknown",
    "available",
    "unavailable",
    "rate_limited",
    "disabled",
]
AIModelMetadataStatus = Literal["discovered", "verified"]
AICostOrigin = Literal["platform", "company"]


class AIModelRecord(BaseModel):
    provider: str
    model_id: str
    capabilities: tuple[AICapability, ...] = Field(default_factory=tuple)
    input_modalities: tuple[str, ...] = Field(default_factory=tuple)
    output_modalities: tuple[str, ...] = Field(default_factory=tuple)
    supported_parameters: tuple[str, ...] = Field(default_factory=tuple)
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
    pricing: JsonObject | None = None
    availability_status: AIAvailabilityStatus = "unknown"
    metadata_status: AIModelMetadataStatus = "discovered"
    last_seen_at: datetime | None = None
    raw: JsonObject = Field(default_factory=dict)

    @property
    def supports_json_schema(self) -> bool:
        return self.supports_structured_output or "response_format" in self.supported_parameters

    @property
    def supports_vision(self) -> bool:
        return "image" in self.input_modalities

    @property
    def supports_image_output(self) -> bool:
        return "image" in self.output_modalities


class AIRuntimeEndpoint(BaseModel):
    provider: str
    capability: AICapability
    base_url: str | None = None
    endpoint_url: str | None = None
    headers: JsonObject = Field(default_factory=dict)
    body: JsonObject = Field(default_factory=dict)


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
