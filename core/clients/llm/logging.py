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
    LOG_LLM_HAS_TOOL_CALLS,
    LOG_LLM_STREAM,
    LOG_LLM_URL,
)

_logger = get_logger(__name__)


def log_llm_stream_response(
    *,
    url: str,
    content: str,
    usage: dict[str, Any],
    reasoning: str | None = None,
    tool_calls: list[Any] | None = None,
) -> None:
    """
    Структурированный лог об агрегированном ответе LLM-стрима.

    Поля выровнены с core.logging.attributes (LOG_LLM_*) и core.tracing.attributes
    (ATTR_LLM_*) для единой схемы между логами и спанами.
    """
    _logger.info(
        EVENT_LLM_STREAM_RESPONSE,
        **{
            LOG_LLM_URL: url,
            LOG_LLM_STREAM: True,
            LOG_LLM_HAS_TOOL_CALLS: bool(tool_calls),
        },
        llm_response_content=content,
        llm_response_reasoning=reasoning,
        llm_response_tool_calls=tool_calls,
        llm_response_usage=usage,
    )
