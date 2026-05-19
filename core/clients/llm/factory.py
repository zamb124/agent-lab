"""Compatibility imports for LLM client construction.

New code should prefer ``core.clients.llm`` for public imports.  This module is
kept because project rules and older callers reference ``factory.get_llm``.
"""

from __future__ import annotations

from typing import Any

from core.clients.llm.client import LLMClient
from core.clients.llm.errors import LLMStreamIdleTimeoutError, LLMStreamUserCancelledError
from core.clients.llm.messages import MessageInput, StreamEvent
from core.clients.llm.mock import MockLLM, _global_mock_registry
from core.clients.llm.runtime import (
    _detect_provider,
    _get_default_base_url,
    _masked_headers,
    _merge_openai_compatible_usage_into_usage_data,
    _message_to_openai,
    _messages_to_openai,
    _resolve_var,
    get_llm,
    get_llm_for_state,
    setup_mock_responses,
    should_use_platform_default_free_pool,
)
from core.company_ai.resolver import resolve_llm_for_capability
from core.company_ai.schema import AICapability
from core.config.testing import is_testing as _is_testing


def _resolve_vision_llm_capability() -> Any | None:
    return resolve_llm_for_capability(AICapability.LLM_VISION)


def get_vision_llm(
    model_name: str = "google/gemini-2.5-flash-preview",
) -> "LLMClient | MockLLM":
    """Создает LLM клиент для vision запросов."""
    if _is_testing():
        mock_key = "mock-gpt-4"
        if mock_key not in _global_mock_registry:
            _global_mock_registry[mock_key] = MockLLM(model_name=mock_key)
        return _global_mock_registry[mock_key]

    del model_name
    resolved_llm = _resolve_vision_llm_capability()
    if resolved_llm is not None:
        return get_llm(
            model_name=resolved_llm.model,
            provider=resolved_llm.provider,
            api_key=resolved_llm.api_key,
            base_url=resolved_llm.base_url,
            folder_id=resolved_llm.folder_id,
            temperature=0.1,
            fallback_models=list(resolved_llm.fallback_models or ()) or None,
        )
    raise ValueError(
        "get_vision_llm требует company override для capability=llm_vision; "
        "скрытый fallback на settings.llm/provider запрещён"
    )


__all__ = [
    "LLMClient",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "MockLLM",
    "StreamEvent",
    "get_llm",
    "get_llm_for_state",
    "get_vision_llm",
    "setup_mock_responses",
    "should_use_platform_default_free_pool",
    "_detect_provider",
    "_get_default_base_url",
    "_masked_headers",
    "_merge_openai_compatible_usage_into_usage_data",
    "_message_to_openai",
    "_messages_to_openai",
    "_resolve_var",
]
