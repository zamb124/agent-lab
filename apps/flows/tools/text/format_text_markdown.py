"""Тул: структурировать текст в Markdown через company LLM capability."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.text_client import TextClient
from core.types import JsonObject


class FormatTextMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, description="Исходный текст.")


@tool(
    name="format_text_markdown",
    description=(
        "Превращает произвольный текст в аккуратный Markdown. "
        "Провайдер и модель берутся из company capability llm_format_markdown."
    ),
    tags=["text"],
    parameters_model=FormatTextMarkdownArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def format_text_markdown(
    text: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    del state
    markdown = await TextClient().format_markdown(text)
    return {"markdown": markdown}
