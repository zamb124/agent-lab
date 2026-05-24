"""Compatibility imports for LLM client construction.

New code should prefer ``core.clients.llm`` for public imports.  This module is
kept because project rules and older callers reference ``factory.get_llm``.
"""

from __future__ import annotations

from core.clients.llm.client import LLMClient
from core.clients.llm.errors import LLMStreamIdleTimeoutError, LLMStreamUserCancelledError
from core.clients.llm.messages import MessageInput, StreamEvent
from core.clients.llm.mock import MockLLM, get_or_create_global_mock_llm
from core.clients.llm.model_routing import split_provider_prefixed_model
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
from core.company_ai.resolver import ResolvedLLM, resolve_llm_for_capability
from core.company_ai.schema import AICapability
from core.config import get_settings
from core.config.testing import is_testing as _is_testing


def _resolve_vision_llm_capability() -> ResolvedLLM | None:
    return resolve_llm_for_capability(AICapability.LLM_VISION)


def _testing_vision_llm() -> ResolvedLLM:
    return ResolvedLLM(provider="mock", model="mock-gpt-4")


def _explicit_vision_llm(model_name: str) -> ResolvedLLM:
    requested_model = model_name.strip()
    if not requested_model:
        raise ValueError("vision_model задан пустой строкой")
    split_provider, split_model = split_provider_prefixed_model(None, requested_model)
    resolved_model = str(split_model or requested_model).strip()
    if not resolved_model:
        raise ValueError("vision_model не удалось разобрать в непустую модель")
    resolved_provider = split_provider or get_settings().llm.provider
    if not str(resolved_provider).strip():
        raise ValueError("settings.llm.provider обязателен для явной vision_model")
    return ResolvedLLM(provider=str(resolved_provider).strip(), model=resolved_model)


def _platform_default_vision_llm() -> ResolvedLLM:
    resolved_llm = resolve_llm_for_capability(
        AICapability.LLM_VISION,
        include_platform_default=True,
    )
    if resolved_llm is None:
        raise ValueError("platform default для llm_vision не настроен")
    return resolved_llm


def resolve_vision_llm(model_name: str | None = None) -> ResolvedLLM:
    """Резолвит vision LLM: явная модель → company capability → platform default."""
    if _is_testing():
        return _testing_vision_llm()
    if model_name is not None:
        return _explicit_vision_llm(model_name)

    resolved_llm = _resolve_vision_llm_capability()
    if resolved_llm is not None:
        return resolved_llm
    return _platform_default_vision_llm()


def create_vision_llm(resolved_llm: ResolvedLLM) -> "LLMClient | MockLLM":
    """Создает LLM клиент для уже зарезолвленной vision capability."""
    if _is_testing():
        return get_or_create_global_mock_llm(resolved_llm.model)
    return get_llm(
        model_name=resolved_llm.model,
        provider=resolved_llm.provider,
        api_key=resolved_llm.api_key,
        base_url=resolved_llm.base_url,
        folder_id=resolved_llm.folder_id,
        temperature=0.1,
        extra_request_headers=resolved_llm.extra_request_headers,
        extra_request_body=resolved_llm.extra_request_body,
        fallback_models=list(resolved_llm.fallback_models or ()) or None,
    )


def get_vision_llm(model_name: str | None = None) -> "LLMClient | MockLLM":
    """Создает LLM клиент для vision запросов."""
    return create_vision_llm(resolve_vision_llm(model_name))


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
    "create_vision_llm",
    "resolve_vision_llm",
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
