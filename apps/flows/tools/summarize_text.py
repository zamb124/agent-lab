"""Тул суммаризации текста через ``get_text_transform_service`` (``get_llm`` внутри сервиса)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.services.platform_facades import get_text_transform_service
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS


class SummarizeTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
        description="Провайдер LLM (openrouter, provider_litserve, …); None — из настроек.",
    )
    model: str | None = Field(
        None,
        description="Модель или префикс `openrouter:vendor/model`; None — default_model.",
    )


@tool(
    name="summarize_text",
    description=(
        "Кратко суммирует текст через платформенный LLM. "
        "Провайдер и модель — как у `get_llm` (в т.ч. `openrouter:…`)."
    ),
    tags=["text", "llm"],
    args_schema=SummarizeTextArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
    mock_response={"summary": "[mock] summarized text"},
)
async def summarize_text(
    text: str,
    max_output_tokens: int | None = None,
    instruction: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, str]:
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
