from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability

AILatencyPreference = Literal["lowest", "balanced", "quality"]
AIQualityPreference = Literal["lowest", "balanced", "highest"]


class AIRequestRequirements(BaseModel):
    tools_required: bool = False
    vision_required: bool = False
    image_output_required: bool = False
    min_context: int | None = None
    json_mode: bool = False
    structured_output: bool = False
    embedding_dimension: int | None = None
    free_only: bool = False
    latency_preference: AILatencyPreference = "balanced"
    quality_preference: AIQualityPreference = "balanced"
    required_input_modalities: tuple[str, ...] = Field(default_factory=tuple)
    required_output_modalities: tuple[str, ...] = Field(default_factory=tuple)
    required_supported_parameters: tuple[str, ...] = Field(default_factory=tuple)


class AISelection(BaseModel):
    provider: str | None = None
    model: str | None = None
    fallback_models: tuple[tuple[str, str], ...] = Field(default_factory=tuple)

    @property
    def is_explicit(self) -> bool:
        return self.provider is not None or self.model is not None


def requirement_rejection_reasons(
    record: AIModelRecord,
    capability: AICapability,
    requirements: AIRequestRequirements,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if capability not in record.capabilities:
        reasons.append("capability")
    if requirements.free_only and record.is_free is not True:
        reasons.append("free_only")
    if requirements.tools_required and not record.supports_tools:
        reasons.append("tools")
    if (requirements.json_mode or requirements.structured_output) and not record.supports_json_schema:
        reasons.append("structured_output")
    if requirements.vision_required and not record.supports_vision:
        reasons.append("vision")
    if requirements.image_output_required and not record.supports_image_output:
        reasons.append("image_output")
    if requirements.min_context is not None:
        if record.context_length is None or record.context_length < requirements.min_context:
            reasons.append("context_length")
    if requirements.embedding_dimension is not None:
        if record.storage_dimension != requirements.embedding_dimension:
            reasons.append("embedding_dimension")
    for modality in requirements.required_input_modalities:
        if modality not in record.input_modalities:
            reasons.append(f"input_modality:{modality}")
    for modality in requirements.required_output_modalities:
        if modality not in record.output_modalities:
            reasons.append(f"output_modality:{modality}")
    for parameter in requirements.required_supported_parameters:
        if parameter not in record.supported_parameters:
            reasons.append(f"parameter:{parameter}")
    return tuple(reasons)


def model_satisfies_requirements(
    record: AIModelRecord,
    capability: AICapability,
    requirements: AIRequestRequirements,
) -> bool:
    return not requirement_rejection_reasons(record, capability, requirements)

