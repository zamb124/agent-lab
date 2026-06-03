"""Тул суммаризации текста через ``get_text_transform_service`` и canonical AI runtime."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.services.platform_facades import get_text_transform_service
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.state import ExecutionState
from core.types import JsonObject


class SummarizeTextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, description="Исходный текст для сжатого пересказа.")
    max_output_tokens: int | None = Field(
        None,
        ge=1,
        description="Лимит токенов ответа; None — дефолт конфигурации модели/LLM.",
    )
    instruction: str | None = Field(
        None,
        description="Системная инструкция вместо стандартной («суммируй кратко…»).",
    )
    provider: str | None = Field(
        None,
        description="Используется только если company override для llm_summarize не задан.",
    )
    model: str | None = Field(
        None,
        description="Используется только если company override для llm_summarize не задан.",
    )


@tool(
    name="summarize_text",
    description=(
        "Кратко суммирует текст через платформенный LLM. "
        "Провайдер и модель сначала берутся из company capability settings."
    ),
    tags=["text", "llm"],
    parameters_model=SummarizeTextArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def summarize_text(
    text: str,
    max_output_tokens: int | None = None,
    instruction: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    state: ExecutionState | None = None,
) -> JsonObject:
    del state
    svc = get_text_transform_service()
    summary = await svc.summarize(
        text,
        max_output_tokens=max_output_tokens,
        instruction=instruction,
        provider=provider,
        model=model,
    )
    return {"summary": summary}
