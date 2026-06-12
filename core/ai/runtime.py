"""Canonical AI runtime facade.

Service code should create executable clients through this module instead of
constructing provider-specific clients directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from a2a.types import Message

from core.ai.embedding_client import AIEmbeddingClient, DeterministicAIEmbeddingClient
from core.ai.llm_config import LLMCallConfig, ReasoningEffort
from core.ai.models import AICostOrigin, ResolvedAIModel
from core.ai.providers import (
    PROVIDER_LITSERVE,
    PROVIDER_LITSERVE_CRAWL,
    AICapability,
    split_provider_prefixed_model,
)
from core.ai.requirements import AIRequestRequirements, AISelection
from core.ai.rerank_client import AIRerankerHTTPClient
from core.ai.resolver import resolve_ai_model
from core.clients.llm.client import LLMClient
from core.clients.llm.messages import MessageInput, StreamEvent
from core.clients.llm.mock import MockLLM, get_or_create_global_mock_llm
from core.clients.llm.runtime import (
    create_llm_transport_client,
    should_use_platform_default_free_pool,
)
from core.clients.speech_override import SpeechOverride
from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.clients.stt_streaming import BaseSTTStreamer
from core.clients.tts_client import BaseTTSClient, TTSResult
from core.clients.tts_streaming import BaseTTSStreamer
from core.clients.vad_client import BaseVADClient
from core.clients.voice_resolver import (
    ResolvedSttSettings,
)
from core.clients.voice_resolver import (
    get_stt_client as _create_stt_client,
)
from core.clients.voice_resolver import (
    get_stt_streamer as _create_stt_streamer,
)
from core.clients.voice_resolver import (
    get_tts_client as _create_tts_client,
)
from core.clients.voice_resolver import (
    get_tts_streamer as _create_tts_streamer,
)
from core.clients.voice_resolver import (
    get_vad_client as _create_vad_client,
)
from core.clients.voice_resolver import (
    invalidate_company_overrides_cache as _invalidate_voice_company_overrides_cache,
)
from core.clients.voice_resolver import (
    invalidate_platform_pronunciation_cache as _invalidate_voice_platform_pronunciation_cache,
)
from core.clients.voice_resolver import (
    reset_voice_resolver_for_tests as _reset_voice_runtime_for_tests,
)
from core.clients.voice_resolver import (
    resolve_effective_tts_voice_for_ws as _resolve_effective_tts_voice_for_ws,
)
from core.clients.voice_resolver import (
    resolve_stt_settings as _resolve_stt_settings,
)
from core.config import get_settings
from core.config.llm_openai_compat import resolve_provider_api_key_for_openai_compatible_calls
from core.config.testing import is_testing
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState


def _string_headers(headers: JsonObject) -> dict[str, str] | None:
    return {key: str(value) for key, value in headers.items()} or None


def create_llm_client_from_ai_model(
    resolved: ResolvedAIModel,
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
    """Create an executable LLM client from the unified AI resolver contract."""
    if resolved.capability not in {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }:
        raise ValueError(f"capability {resolved.capability.value!r} is not executable as LLM")
    if resolved.model is None or not resolved.model.strip():
        raise ValueError(f"capability {resolved.capability.value}: resolved LLM model is empty")
    if resolved.provider is None or not resolved.provider.strip():
        raise ValueError(f"capability {resolved.capability.value}: resolved LLM provider is empty")
    return create_llm_transport_client(
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
        extra_request_headers=_string_headers(resolved.headers),
        extra_request_body=resolved.body or None,
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
    selection = (
        AISelection(provider=fallback_provider, model=fallback_model)
        if fallback_provider is not None and fallback_model is not None
        else None
    )
    resolved = resolve_ai_model(
        capability,
        selection=selection,
        include_platform_default=include_platform_default,
    )
    if resolved is None:
        raise ValueError(f"AI capability {capability.value}: LLM route не настроен")
    merged_fallbacks: Sequence[LLMCallConfig | JsonObject] | None = (
        fallback_models if fallback_models is not None else resolved.fallback_models
    )
    resolved_with_fallbacks = resolved.model_copy(
        update={"fallback_models": tuple(merged_fallbacks or ())}
    )
    return create_llm_client_from_ai_model(
        resolved_with_fallbacks,
        temperature=temperature,
        max_tokens=max_tokens,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
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
        return create_llm_transport_client(
            state=state,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
        )
    return create_llm_transport_client(
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


def _testing_vision_ai_model() -> ResolvedAIModel:
    return ResolvedAIModel(
        capability=AICapability.LLM_VISION,
        provider="mock",
        model="mock-gpt-4",
    )


def _explicit_vision_ai_model(model_name: str) -> ResolvedAIModel:
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
    resolved = resolve_ai_model(
        AICapability.LLM_VISION,
        selection=AISelection(
            provider=str(resolved_provider).strip(),
            model=resolved_model,
        ),
        include_platform_default=False,
    )
    if resolved is None:
        raise ValueError("vision_model не удалось разрешить")
    return resolved


def resolve_vision_ai_model(model_name: str | None = None) -> ResolvedAIModel:
    """Resolve vision through the canonical ``llm_vision`` capability."""
    if is_testing():
        return _testing_vision_ai_model()
    if model_name is not None:
        return _explicit_vision_ai_model(model_name)
    resolved = resolve_ai_model(AICapability.LLM_VISION, include_platform_default=False)
    if resolved is not None:
        return resolved
    platform_default = resolve_ai_model(AICapability.LLM_VISION, include_platform_default=True)
    if platform_default is None:
        raise ValueError("platform default для llm_vision не настроен")
    return platform_default


def create_vision_llm_client(resolved: ResolvedAIModel) -> LLMClient | MockLLM:
    """Create a vision LLM client from the canonical ``llm_vision`` model."""
    if resolved.capability != AICapability.LLM_VISION:
        raise ValueError(f"capability {resolved.capability.value!r} is not executable as vision")
    if resolved.model is None or not resolved.model.strip():
        raise ValueError("vision LLM model пуст")
    if is_testing():
        return get_or_create_global_mock_llm(resolved.model)
    return create_llm_client_from_ai_model(
        resolved,
        temperature=0.1,
        allow_platform_paid_fallback=True,
    )


def create_embedding_client_from_runtime(
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str | None = None,
    timeout: int = 15,
    dimension: int | None = None,
    mrl_output_dimension: int | None = None,
    extra_headers: dict[str, str] | None = None,
    deterministic: bool = False,
) -> AIEmbeddingClient:
    """Create the low-level embeddings transport through the AI runtime facade."""
    resolved_api_key = api_key
    if resolved_api_key is None or not resolved_api_key.strip():
        if provider in {PROVIDER_LITSERVE, PROVIDER_LITSERVE_CRAWL}:
            resolved_api_key = PROVIDER_LITSERVE_PLACEHOLDER_BEARER
        else:
            resolved_api_key = resolve_provider_api_key_for_openai_compatible_calls(
                get_settings().llm,
                provider,
            )
    client_class = DeterministicAIEmbeddingClient if deterministic else AIEmbeddingClient
    return client_class(
        api_key=resolved_api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        dimension=dimension,
        mrl_output_dimension=mrl_output_dimension,
        extra_headers=extra_headers,
    )


def create_embedding_client_from_ai_model(
    resolved: ResolvedAIModel,
    *,
    timeout: int = 15,
) -> AIEmbeddingClient:
    """Create an embedding client from the unified AI resolver contract."""
    if resolved.capability != AICapability.EMBEDDING:
        raise ValueError(f"capability {resolved.capability.value!r} is not executable as embedding")
    if resolved.model is None or not resolved.model.strip():
        raise ValueError("embedding model is empty")
    if resolved.provider is None or not resolved.provider.strip():
        raise ValueError("embedding provider is empty")
    return create_embedding_client_from_runtime(
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        timeout=timeout,
        dimension=resolved.dimension,
        mrl_output_dimension=resolved.mrl_output_dimension,
        extra_headers=_string_headers(resolved.headers),
    )


async def embed_texts(
    texts: list[str],
    *,
    requirements: AIRequestRequirements | None = None,
    selection: AISelection | None = None,
    timeout: int = 15,
) -> list[list[float]]:
    """Resolve the embedding capability and generate vectors through one runtime API."""
    resolved = resolve_ai_model(
        AICapability.EMBEDDING,
        requirements=requirements,
        selection=selection,
        include_platform_default=True,
    )
    if resolved is None:
        raise ValueError("AI capability embedding: route не настроен")
    client = create_embedding_client_from_ai_model(resolved, timeout=timeout)
    return await client.generate_embeddings(texts)


async def rerank_scores(
    *,
    endpoint_url: str,
    query: str,
    passages: list[str],
    timeout_seconds: float = 60.0,
    cost_per_1m_tokens: float = 5.0,
    platform_markup: float = 1.1,
    billing_resource_id: str = "rerank",
    cost_origin: AICostOrigin = "platform",
    model: str | None = None,
    api_key: str | None = None,
    extra_request_headers: dict[str, str] | None = None,
) -> list[float]:
    """Execute rerank through the canonical AI runtime facade."""
    client = AIRerankerHTTPClient(
        timeout_seconds=timeout_seconds,
        cost_per_1m_tokens=cost_per_1m_tokens,
        platform_markup=platform_markup,
        billing_resource_id=billing_resource_id,
        cost_origin=cost_origin,
        model=model,
        api_key=api_key,
        extra_request_headers=extra_request_headers,
    )
    return await client.rerank_scores(endpoint_url, query, passages)


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


async def create_voice_stt_client(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
) -> BaseSTTClient:
    """Create a speech-to-text client through the canonical AI runtime boundary."""
    return await _create_stt_client(company_id=company_id, override=override)


async def create_voice_tts_client(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
) -> BaseTTSClient:
    """Create a text-to-speech client through the canonical AI runtime boundary."""
    return await _create_tts_client(company_id=company_id, override=override)


async def create_voice_vad_client(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
) -> BaseVADClient:
    """Create a voice-activity-detection client through the canonical AI runtime boundary."""
    return await _create_vad_client(company_id=company_id, override=override)


async def create_voice_stt_streamer(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
    sample_rate: int = 16000,
) -> BaseSTTStreamer:
    """Create a streaming STT adapter through the canonical AI runtime boundary."""
    return await _create_stt_streamer(
        company_id=company_id,
        override=override,
        sample_rate=sample_rate,
    )


async def create_voice_tts_streamer(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
) -> BaseTTSStreamer:
    """Create a streaming TTS adapter through the canonical AI runtime boundary."""
    return await _create_tts_streamer(company_id=company_id, override=override)


async def resolve_voice_stt_settings(
    *,
    company_id: str,
    override: SpeechOverride | None = None,
) -> ResolvedSttSettings:
    """Resolve STT settings through the canonical AI runtime boundary."""
    return await _resolve_stt_settings(company_id=company_id, override=override)


async def resolve_voice_tts_ws_voice(
    *,
    company_id: str | None,
    flow_tts: SpeechOverride,
) -> str | None:
    """Resolve the effective TTS voice for voice WebSocket URLs through ``core.ai``."""
    return await _resolve_effective_tts_voice_for_ws(
        company_id=company_id,
        flow_tts=flow_tts,
    )


async def transcribe_audio_bytes(
    *,
    company_id: str,
    audio_bytes: bytes,
    file_name: str,
    content_type: str,
    override: SpeechOverride | None = None,
    language: str | None = None,
) -> STTTranscriptionResult:
    """Transcribe audio bytes through the canonical AI runtime boundary."""
    client = await create_voice_stt_client(company_id=company_id, override=override)
    return await client.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=file_name,
        content_type=content_type,
        language=language,
    )


async def synthesize_speech_audio(
    *,
    company_id: str,
    text: str,
    override: SpeechOverride | None = None,
    voice: str | None = None,
    response_format: str | None = None,
    sample_rate: int | None = None,
) -> TTSResult:
    """Synthesize speech through the canonical AI runtime boundary."""
    client = await create_voice_tts_client(company_id=company_id, override=override)
    return await client.synthesize(
        text=text,
        voice=voice,
        response_format=response_format,
        sample_rate=sample_rate,
    )


def invalidate_voice_company_overrides_cache(company_id: str) -> None:
    """Invalidate cached company voice overrides behind the ``core.ai`` runtime."""
    _invalidate_voice_company_overrides_cache(company_id)


def invalidate_voice_platform_pronunciation_cache() -> None:
    """Invalidate cached platform pronunciation rules behind the ``core.ai`` runtime."""
    _invalidate_voice_platform_pronunciation_cache()


def reset_voice_runtime_for_tests() -> None:
    """Reset voice runtime caches for tests."""
    _reset_voice_runtime_for_tests()


__all__ = [
    "StreamEvent",
    "chat_for_capability",
    "create_embedding_client_from_ai_model",
    "create_embedding_client_from_runtime",
    "create_llm_client_from_ai_model",
    "create_llm_client_from_call_config",
    "create_llm_client_for_capability",
    "create_vision_llm_client",
    "create_voice_stt_client",
    "create_voice_stt_streamer",
    "create_voice_tts_client",
    "create_voice_tts_streamer",
    "create_voice_vad_client",
    "embed_texts",
    "invalidate_voice_company_overrides_cache",
    "invalidate_voice_platform_pronunciation_cache",
    "rerank_scores",
    "resolve_vision_ai_model",
    "resolve_voice_stt_settings",
    "resolve_voice_tts_ws_voice",
    "reset_voice_runtime_for_tests",
    "should_use_platform_default_free_pool",
    "synthesize_speech_audio",
    "transcribe_audio_bytes",
]
