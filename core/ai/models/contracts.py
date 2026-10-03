"""Контракты каталога моделей без таблиц."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.ai.providers import AICapability
from core.types import JsonObject

AIAvailabilityStatus = Literal[
    "unknown",
    "available",
    "unavailable",
    "disabled",
]
AIModelMetadataStatus = Literal["discovered", "verified"]
AICostOrigin = Literal["platform", "company"]


class ArtificialAnalysisIndices(BaseModel):
    intelligence_index: float
    coding_index: float | None = None
    agentic_index: float | None = None
    model_permaslug: str

class AIRuntimeEndpoint(BaseModel):
    provider: str
    capability: AICapability
    base_url: str | None = None
    endpoint_url: str | None = None
    headers: JsonObject = Field(default_factory=dict)
    body: JsonObject = Field(default_factory=dict)
