"""Тул суммаризации текста через capability text.summarize (capability-gateway)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.runners.capability_context import capability_execution_context
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.capabilities import CapabilityCallRequest
from core.clients.capability_gateway_client import CapabilityGatewayClient
from core.types import JsonObject, require_json_object


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
        "Провайдер и модель сначала берутся из company capability settings. "
        "Исполнение — capability text.summarize через capability-gateway."
    ),
    tags=["text"],
    parameters_model=SummarizeTextArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def summarize_text(
    text: str,
    max_output_tokens: int | None = None,
    instruction: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    *,
    state: ExecutionState,
) -> JsonObject:
    kwargs: JsonObject = {"text": text}
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if instruction is not None:
        kwargs["instruction"] = instruction
    if provider is not None:
        kwargs["provider"] = provider
    if model is not None:
        kwargs["model"] = model
    timeout = float(get_flows_settings().node_execution_wall_time_cap_seconds)
    execution_context = capability_execution_context(
        state,
        allowed_capabilities=["text.summarize"],
    )
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="text.summarize",
            kwargs=kwargs,
        ),
        timeout=timeout,
    )
    result = require_json_object(response.result, "summarize_text.result")
    summary = result.get("summary")
    if not isinstance(summary, str):
        raise RuntimeError("text.summarize returned invalid result")
    return {"summary": summary}
