"""HTTP/WS контракты preview-рендера промпта: один payload на REST и command-router."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.types import JsonObject


class RenderPromptRequest(StrictBaseModel):
    prompt: str = Field(min_length=1)
    variables: JsonObject | None = None


class RenderPromptResponse(StrictBaseModel):
    rendered: str
    used_variables: list[str]
