"""Тул: структурировать текст в Markdown (LitServe HTTP по умолчанию или ``get_llm``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.services.platform_facades import get_text_transform_service
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.state import ExecutionState
from core.types import JsonObject


class FormatTextMarkdownArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, description="Исходный текст.")
    provider: str | None = Field(
        None,
        description=(
            "Используется только если company override для llm_format_markdown не задан. "
            "`provider_litserve` — старый LitServe HTTP; иначе — явный LLM-провайдер."
        ),
    )
    model: str | None = Field(
        None,
        description="Модель; для LitServe — api id локальной LLM; для OpenRouter — `openrouter:slug` или пара provider+model.",
    )
    max_chunk_chars: int | None = Field(
        None,
        ge=512,
        le=100_000,
        description="Размер чанка; None — из `provider_litserve.infra.markdown_max_chunk_chars`.",
    )


@tool(
    name="format_text_markdown",
    description=(
        "Превращает произвольный текст в аккуратный Markdown. "
        "Провайдер и модель сначала берутся из company capability settings."
    ),
    tags=["text", "markdown"],
    args_schema=FormatTextMarkdownArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
    mock_response={"markdown": "# [mock]\n\nFormatted in tests."},
)
async def format_text_markdown(
    text: str,
    provider: str | None = None,
    model: str | None = None,
    max_chunk_chars: int | None = None,
    state: ExecutionState | None = None,
) -> JsonObject:
    del state
    svc = get_text_transform_service()
    markdown = await svc.format_markdown(
        text,
        provider=provider,
        model=model,
        max_chunk_chars=max_chunk_chars,
    )
    return {"markdown": markdown}
