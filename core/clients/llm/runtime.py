"""
LLM client runtime composition root.

Stream-first architecture: all runtime LLM calls go through ``get_llm`` and
``LLMClient.stream``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.clients.llm.client import LLMClient
from core.clients.llm.config import LLMCallConfig, ReasoningEffort
from core.clients.llm.errors import LLMStreamIdleTimeoutError, LLMStreamUserCancelledError
from core.clients.llm.messages import (
    MessageInput,
    StreamEvent,
)
from core.clients.llm.messages import (
    message_to_openai as _message_to_openai,
)
from core.clients.llm.messages import (
    messages_to_openai as _messages_to_openai,
)
from core.clients.llm.mock import MockLLM, _global_mock_registry, get_global_mock_llm
from core.clients.llm.model_routing import split_provider_prefixed_model
from core.clients.llm.openai_compat import (
    masked_headers as _masked_headers,
)
from core.clients.llm.openai_compat import (
    merge_openai_compatible_usage_into_usage_data as _merge_openai_compatible_usage_into_usage_data,
)
from core.clients.llm.platform_pool import _make_platform_default_candidate_resolver
from core.clients.llm.provider_resolution import (
    _detect_provider,
    _get_default_base_url,
    _is_humanitec_llm_provider,
    _platform_default_pool_is_configured,
    _resolve_headers_vars,
    _resolve_llm_call_config,
    _resolve_var,
    _resolved_llm_configs,
    _should_use_platform_default_pool,
)
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.testing import is_testing as _is_testing
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)


def should_use_platform_default_free_pool(
    *,
    model_name: Optional[str],
    provider: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    folder_id: Optional[str],
    settings: BaseSettings,
) -> bool:
    """Public predicate for callers that must decide billing before creating a client."""
    return _should_use_platform_default_pool(
        model=model_name,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        settings=settings,
    )


def get_llm(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    folder_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    state: Optional["ExecutionState"] = None,
    fallback_models: Optional[List[LLMCallConfig]] = None,
    allow_platform_paid_fallback: bool = True,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    seed: Optional[int] = None,
    reasoning_effort: Optional[ReasoningEffort] = None,
    extra_request_body: Optional[Dict[str, Any]] = None,
    extra_request_headers: Optional[Dict[str, str]] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент.

    Args:
        model_name: Имя модели
        temperature: Температура
        provider: Провайдер (openai, openrouter, bothub, provider_litserve, yandex,
            humanitec_llm)
        api_key: API ключ (напрямую или @var:my_key)
        base_url: Base URL провайдера (напрямую или @var:my_url)
        folder_id: Каталог Yandex Cloud (yandex); иначе из llm.yandex.folder_id
        max_tokens: Лимит токенов ответа (если None — из настроек модели / глобальных)
        state: ExecutionState для резолюции @var:
        fallback_models: Ordered list of full LLMCallConfig fallback attempts.
        allow_platform_paid_fallback: Для платформенного default-route через free-pool
            разрешает последний платный fallback. Рантайм flows выключает его при
            неположительном балансе, чтобы бесплатные модели не блокировались pre-flight биллингом.
    """
    settings = get_settings()
    testing = _is_testing()

    split_provider, split_model = split_provider_prefixed_model(provider, model_name)
    if split_provider is not None:
        provider = split_provider
    model = split_model if split_model is not None else model_name

    if _should_use_platform_default_pool(
        model=model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        settings=settings,
    ) and not testing:
        paid_fallback_model = settings.llm.openrouter_free_pool.fallback_model.strip()
        resolved_temperature = temperature if temperature is not None else settings.llm.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        primary_candidate = _resolve_llm_call_config(
            LLMCallConfig(
                provider="openrouter",
                model=paid_fallback_model or settings.llm.default_model,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
                top_p=top_p,
                top_k=top_k,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                seed=seed,
                reasoning_effort=reasoning_effort,
                extra_request_body=extra_request_body,
                extra_request_headers=extra_request_headers,
                source="platform_paid_fallback",
            ),
            settings=settings,
            state=state,
            source="platform_paid_fallback",
        )
        return LLMClient(
            model=str(primary_candidate.model),
            api_key=str(primary_candidate.api_key),
            base_url=primary_candidate.base_url,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            timeout=settings.llm.timeout,
            default_headers=dict(primary_candidate.default_headers),
            llm_provider=primary_candidate.provider,
            candidates=[primary_candidate] if allow_platform_paid_fallback else [],
            candidate_resolver=_make_platform_default_candidate_resolver(
                settings,
                include_paid_fallback=allow_platform_paid_fallback,
            ),
            first_token_timeout=settings.llm.openrouter_free_pool.first_token_timeout_seconds,
            candidate_cooldown_seconds=settings.llm.openrouter_free_pool.candidate_cooldown_seconds,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=allow_platform_paid_fallback,
            top_p=top_p,
            top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_request_body=extra_request_body,
            extra_request_headers=_resolve_headers_vars(extra_request_headers, state),
        )

    if testing and _is_humanitec_llm_provider(provider):
        provider = None
        model = "mock-gpt-4"

    if _is_humanitec_llm_provider(provider):
        if any(
            value is not None and str(value).strip()
            for value in (api_key, base_url, folder_id)
        ):
            raise ValueError(
                "humanitec_llm: api_key/base_url/folder_id не задаются — это виртуальный "
                "провайдер платформы"
            )
        if not _platform_default_pool_is_configured(settings):
            raise ValueError(
                "humanitec_llm недоступен: включите llm.openrouter_free_pool и настройте "
                "llm.openrouter.api_key"
            )

    model = model or settings.llm.default_model
    if testing and model and not model.startswith("mock-"):
        logger.warning("llm.testing_model_replaced", original_model=model, replacement_model="mock-gpt-4")
        model = "mock-gpt-4"

    if model.startswith("mock-"):
        if model not in _global_mock_registry:
            _global_mock_registry[model] = MockLLM(model_name=model)
        return _global_mock_registry[model]

    model_config = settings.llm.models.get(model)
    resolved_temperature = (
        temperature
        if temperature is not None
        else (model_config.temperature if model_config else settings.llm.temperature)
    )
    resolved_max_tokens = (
        max_tokens
        if max_tokens is not None
        else (model_config.max_tokens if model_config else settings.llm.max_tokens)
    )
    timeout = settings.llm.timeout

    primary_config = LLMCallConfig(
        provider=provider,
        model=model,
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
        api_key=api_key,
        folder_id=folder_id,
        base_url=base_url,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=extra_request_headers,
        source="explicit",
    )
    candidates = _resolved_llm_configs(
        primary_config,
        fallback_models,
        settings=settings,
        state=state,
    )
    primary_candidate = candidates[0]

    if primary_config.api_key:
        logger.info(
            "llm.custom_api_key_configured",
            provider=primary_candidate.provider,
            base_url=primary_candidate.base_url,
        )

    return LLMClient(
        model=str(primary_candidate.model),
        api_key=str(primary_candidate.api_key),
        base_url=primary_candidate.base_url,
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
        timeout=timeout,
        default_headers=dict(primary_candidate.default_headers),
        llm_provider=primary_candidate.provider,
        candidates=candidates,
        first_token_timeout=settings.llm.openrouter_free_pool.first_token_timeout_seconds,
        candidate_cooldown_seconds=settings.llm.openrouter_free_pool.candidate_cooldown_seconds,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=_resolve_headers_vars(extra_request_headers, state),
    )


def get_llm_for_state(
    state: Optional["ExecutionState"] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    folder_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    fallback_models: Optional[List[LLMCallConfig]] = None,
    allow_platform_paid_fallback: bool = True,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    seed: Optional[int] = None,
    reasoning_effort: Optional[ReasoningEffort] = None,
    extra_request_body: Optional[Dict[str, Any]] = None,
    extra_request_headers: Optional[Dict[str, str]] = None,
) -> LLMClient | MockLLM:
    """Создает LLM клиент с учётом mock конфига из state."""
    if state:
        mock_config = getattr(state, "mock", None)
        mock_responses = None
        if isinstance(mock_config, dict) and mock_config.get("enabled"):
            llm_responses = mock_config.get("llm")
            if llm_responses:
                mock_responses = llm_responses
        if mock_responses:
            mock = MockLLM(model_name=model_name or "mock-gpt-4")
            mock.configure(response_queue=mock_responses)
            return mock

    return get_llm(
        model_name=model_name,
        temperature=temperature,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        max_tokens=max_tokens,
        fallback_models=fallback_models,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=extra_request_headers,
        state=state,
    )


def setup_mock_responses(
    responses: Optional[Dict[str, str]] = None,
    tool_responses: Optional[Dict[str, Dict[str, Any]]] = None,
    default_response: Optional[str] = None,
    response_queue: Optional[List[Any]] = None,
    model_name: str = "mock-gpt-4",
) -> MockLLM:
    """Настройка mock ответов для тестов (локальная очередь)."""
    _ = get_llm(model_name)
    mock_llm = get_global_mock_llm(model_name)
    if mock_llm is None:
        raise RuntimeError(f"Mock LLM не зарегистрирован: {model_name}")

    mock_llm.reset()
    mock_llm.configure(
        response_queue=response_queue,
        tool_responses=tool_responses,
        responses=responses,
        default_response=default_response,
    )

    return mock_llm


__all__ = [
    "LLMClient",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "MessageInput",
    "MockLLM",
    "StreamEvent",
    "get_llm",
    "get_llm_for_state",
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
