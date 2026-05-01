"""
Доменные шаблоны structured-логов для LLM-клиентов.

Хранятся вне core.logging, потому что доменные данные принадлежат слою
LLM-клиентов. core.logging остаётся универсальным транспортом.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from core.logging.attributes import (
    EVENT_LLM_STREAM_RESPONSE,
    LOG_LLM_DURATION_MS,
    LOG_LLM_HAS_TOOL_CALLS,
    LOG_LLM_INPUT_TOKENS,
    LOG_LLM_MODEL,
    LOG_LLM_OUTPUT_TOKENS,
    LOG_LLM_PROVIDER,
    LOG_LLM_STREAM,
    LOG_LLM_TOTAL_TOKENS,
    LOG_LLM_URL,
)

_logger = get_logger(__name__)


def log_llm_stream_response(
    *,
    url: str,
    content: str,
    usage: dict[str, Any],
    provider: str | None = None,
    model: str | None = None,
    duration_ms: float | None = None,
    reasoning: str | None = None,
    tool_calls: list[Any] | None = None,
) -> None:
    """
    Структурированный лог об агрегированном ответе LLM-стрима.

    Поля выровнены с core.logging.attributes (LOG_LLM_*) и core.tracing.attributes
    (ATTR_LLM_*) для единой схемы между логами и спанами.
    """
    fields: dict[str, Any] = {
        LOG_LLM_URL: url,
        LOG_LLM_STREAM: True,
        LOG_LLM_HAS_TOOL_CALLS: bool(tool_calls),
    }
    if provider is not None:
        fields[LOG_LLM_PROVIDER] = provider
    if model is not None:
        fields[LOG_LLM_MODEL] = model
    if duration_ms is not None:
        fields[LOG_LLM_DURATION_MS] = round(duration_ms, 2)

    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    total_tokens = usage.get("total_tokens") or (input_tokens + output_tokens)
    fields[LOG_LLM_INPUT_TOKENS] = input_tokens
    fields[LOG_LLM_OUTPUT_TOKENS] = output_tokens
    fields[LOG_LLM_TOTAL_TOKENS] = total_tokens

    _logger.info(
        EVENT_LLM_STREAM_RESPONSE,
        **fields,
        llm_response_content=content,
        llm_response_reasoning=reasoning,
        llm_response_tool_calls=tool_calls,
        llm_response_usage=usage,
    )
