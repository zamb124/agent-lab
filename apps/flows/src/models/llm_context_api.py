"""HTTP/WS контракты parent LLM context: один payload на REST и command-router."""

from __future__ import annotations

from core.models import StrictBaseModel
from core.types import JsonObject


class LlmContextResolveParentRequest(StrictBaseModel):
    llm_context_resource_key: str | None = None
    flow_resources: dict[str, JsonObject] = {}
    node_resources: dict[str, JsonObject] = {}


class LlmContextResolveParentResponse(StrictBaseModel):
    resolved: JsonObject
    profiles: list[str]
    budgets: list[str]
