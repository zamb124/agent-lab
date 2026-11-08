"""Тул: структурировать текст в Markdown через capability text.format_markdown (capability-gateway)."""

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


class FormatTextMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, description="Исходный текст.")


@tool(
    name="format_text_markdown",
    description=(
        "Превращает произвольный текст в аккуратный Markdown. "
        "Провайдер и модель берутся из company capability llm_format_markdown. "
        "Исполнение — capability text.format_markdown через capability-gateway."
    ),
    tags=["text"],
    parameters_model=FormatTextMarkdownArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def format_text_markdown(
    text: str,
    *,
    state: ExecutionState,
) -> JsonObject:
    timeout = float(get_flows_settings().node_execution_wall_time_cap_seconds)
    execution_context = capability_execution_context(
        state,
        allowed_capabilities=["text.format_markdown"],
    )
    response = await CapabilityGatewayClient().call(
        CapabilityCallRequest(
            context=execution_context,
            name="text.format_markdown",
            kwargs={"text": text},
        ),
        timeout=timeout,
    )
    result = require_json_object(response.result, "format_text_markdown.result")
    markdown = result.get("markdown")
    if not isinstance(markdown, str):
        raise RuntimeError("text.format_markdown returned invalid result")
    return {"markdown": markdown}
