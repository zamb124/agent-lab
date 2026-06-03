"""Canonical AI runtime facade.

Service code should create executable clients through this module instead of
constructing provider-specific clients directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from a2a.types import Message

from core.ai.providers import PROVIDER_LITSERVE, AICapability
from core.ai.resolver import ResolvedEmbedding, ResolvedLLM, resolve_llm_for_capability
from core.clients.llm.client import LLMClient
from core.clients.llm.config import LLMCallConfig, ReasoningEffort
from core.clients.llm.factory import get_llm
from core.clients.llm.messages import MessageInput, StreamEvent
from core.clients.llm.mock import MockLLM
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_api_key_for_openai_compatible_calls
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.rag.services.embedding_service import EmbeddingService
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState


def create_llm_client(
    resolved: ResolvedLLM,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    state: "ExecutionState | None" = None,
    allow_platform_paid_fallback: bool = True,
    top_p: float | None = None,
    top_k: int | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    seed: int | None = None,
    reasoning_effort: ReasoningEffort | None = None,
) -> LLMClient | MockLLM:
    """Create an executable LLM client from an already resolved capability."""
    return get_llm(
        model_name=resolved.model,
        provider=resolved.provider,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        folder_id=resolved.folder_id,
        temperature=temperature,
        max_tokens=max_tokens,
        state=state,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_headers=resolved.extra_request_headers,
        extra_request_body=resolved.extra_request_body,
        fallback_models=list(resolved.fallback_models or ()) or None,
    )


def create_llm_client_for_capability(
    capability: AICapability,
    *,
    include_platform_default: bool = True,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    allow_platform_paid_fallback: bool = True,
    top_p: float | None = None,
    top_k: int | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    seed: int | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None = None,
) -> LLMClient | MockLLM:
    """Resolve and create an LLM client for a capability."""
    resolved = resolve_llm_for_capability(
        capability,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        include_platform_default=include_platform_default,
    )
    if resolved is None:
        raise ValueError(f"AI capability {capability.value}: LLM route не настроен")
    merged_fallbacks: Sequence[LLMCallConfig | JsonObject] | None = (
        fallback_models if fallback_models is not None else resolved.fallback_models
    )
    return get_llm(
        model_name=resolved.model,
        provider=resolved.provider,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        folder_id=resolved.folder_id,
        temperature=temperature,
        max_tokens=max_tokens,
        fallback_models=list(merged_fallbacks or ()) or None,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_headers=resolved.extra_request_headers,
        extra_request_body=resolved.extra_request_body,
    )


def create_llm_client_from_call_config(
    config: LLMCallConfig | None,
    *,
    state: "ExecutionState | None" = None,
    fallback_models: Sequence[LLMCallConfig | JsonObject] | None = None,
    allow_platform_paid_fallback: bool = True,
) -> LLMClient | MockLLM:
    """Create an LLM client from an explicit per-call config."""
    if config is None:
        return get_llm(
            state=state,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
        )
    return get_llm(
        model_name=config.model,
        provider=config.provider,
        api_key=config.api_key,
        base_url=config.base_url,
        folder_id=config.folder_id,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        state=state,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=config.top_p,
        top_k=config.top_k,
        frequency_penalty=config.frequency_penalty,
        presence_penalty=config.presence_penalty,
        seed=config.seed,
        reasoning_effort=config.reasoning_effort,
        extra_request_headers=config.extra_request_headers,
        extra_request_body=config.extra_request_body,
        fallback_models=list(fallback_models or ()) or None,
    )


def create_embedding_client(resolved: ResolvedEmbedding, *, timeout: int = 15) -> EmbeddingService:
    """Create an embedding client from a resolved embedding capability."""
    api_key = resolved.api_key
    if api_key is None or not api_key.strip():
        if resolved.provider == PROVIDER_LITSERVE:
            api_key = PROVIDER_LITSERVE_PLACEHOLDER_BEARER
        else:
            api_key = resolve_provider_api_key_for_openai_compatible_calls(
                get_settings().llm,
                resolved.provider,
            )
    return EmbeddingService(
        api_key=api_key,
        model=resolved.model,
        base_url=resolved.base_url,
        timeout=timeout,
        dimension=resolved.dimension,
        mrl_output_dimension=resolved.mrl_output_dimension,
        extra_headers=resolved.extra_request_headers,
    )


async def chat_for_capability(
    capability: AICapability,
    messages: MessageInput,
    *,
    include_platform_default: bool = True,
    llm_context: JsonObject | None = None,
) -> Message:
    """Convenience one-shot chat through capability resolution."""
    client = create_llm_client_for_capability(
        capability,
        include_platform_default=include_platform_default,
    )
    return await client.chat(messages, llm_context=llm_context)


__all__ = [
    "StreamEvent",
    "chat_for_capability",
    "create_embedding_client",
    "create_llm_client",
    "create_llm_client_from_call_config",
    "create_llm_client_for_capability",
]
