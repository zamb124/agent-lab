"""Canonical AI provider/capability catalog for the whole platform.

The catalog is independent from company settings and runtime clients. It is the
single source of truth for provider visibility in settings UI, model discovery
and capability validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from core.ai.providers.specs import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    GITHUB_MODELS_API_VERSION,
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    HUMANITEC_LLMS_DISPLAY_LABEL,
    LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER,
    LLM_PROVIDER_DEFAULT_BASE_URLS,
    LLM_PROVIDER_DEFAULT_MODELS_URLS,
    LLM_PROVIDER_DETECTION_HOSTS,
    LLM_PROVIDER_SMOKE_MODELS,
    LLM_ROUTING_PROVIDER_SLUGS,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    PLATFORM_LLM_PROVIDER_ORDER,
    PLATFORM_LLM_PROVIDER_SLUGS,
    ZERO_PRICE_LLM_PROVIDER_SLUGS,
    humanitec_llms_model_ref,
    split_humanitec_llms_model_ref,
    split_provider_prefixed_model,
)


class AICapability(str, Enum):
    """Capability is the functional AI role, not the transport provider."""

    LLM_CHAT = "llm_chat"
    LLM_SUMMARIZE = "llm_summarize"
    LLM_FORMAT_MARKDOWN = "llm_format_markdown"
    LLM_CODEGEN = "llm_codegen"
    LLM_VISION = "llm_vision"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    IMAGE_GEN = "image_gen"
    VOICE_STT = "voice_stt"
    VOICE_TTS = "voice_tts"
    VOICE_VAD = "voice_vad"


AIProviderKind = Literal["virtual", "platform"]

PROVIDER_LITSERVE = "provider_litserve"
PROVIDER_LITSERVE_CRAWL = "provider_litserve_crawl"
VOICE_PROVIDER_LITSERVE = "litserve"
HUMANITEC_MODELS_DISPLAY_LABEL = "Humanitec"
HUMANITEC_VOICE_DISPLAY_LABEL = "Humanitec Voice"

LLM_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability.LLM_CHAT,
    AICapability.LLM_SUMMARIZE,
    AICapability.LLM_FORMAT_MARKDOWN,
    AICapability.LLM_CODEGEN,
    AICapability.LLM_VISION,
    AICapability.IMAGE_GEN,
)
LLM_CAPABILITY_VALUES: frozenset[str] = frozenset(cap.value for cap in LLM_CAPABILITIES)

VOICE_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability.VOICE_STT,
    AICapability.VOICE_TTS,
    AICapability.VOICE_VAD,
)
VOICE_CAPABILITY_VALUES: frozenset[str] = frozenset(cap.value for cap in VOICE_CAPABILITIES)

EMBEDDING_PROVIDER_ORDER: tuple[str, ...] = (
    "openrouter",
    "openai",
    "bothub",
    "google",
    "huggingface",
    "deepinfra",
)
EMBEDDING_PROVIDER_SLUGS: frozenset[str] = frozenset(EMBEDDING_PROVIDER_ORDER)

RERANK_PROVIDER_ORDER: tuple[str, ...] = (
    "openrouter",
)
RERANK_PROVIDER_SLUGS: frozenset[str] = frozenset(RERANK_PROVIDER_ORDER)


@dataclass(frozen=True)
class PlatformProviderSpec:
    provider: str
    label: str
    kind: AIProviderKind
    capabilities: frozenset[AICapability]
    byok_allowed: bool = True


_OPENAI_COMPATIBLE_LLM_CAPABILITIES = frozenset(LLM_CAPABILITIES)


def _openai_compatible_provider_capabilities(provider: str) -> frozenset[AICapability]:
    capabilities: set[AICapability] = set(_OPENAI_COMPATIBLE_LLM_CAPABILITIES)
    if provider in EMBEDDING_PROVIDER_SLUGS:
        capabilities.add(AICapability.EMBEDDING)
    if provider in RERANK_PROVIDER_SLUGS:
        capabilities.add(AICapability.RERANK)
    return frozenset(capabilities)


PLATFORM_PROVIDER_SPECS: tuple[PlatformProviderSpec, ...] = (
    PlatformProviderSpec(
        provider=HUMANITEC_LLM_PROVIDER,
        label=HUMANITEC_LLMS_DISPLAY_LABEL,
        kind="virtual",
        capabilities=frozenset(LLM_CAPABILITIES),
        byok_allowed=False,
    ),
    *(
        PlatformProviderSpec(
            provider=provider,
            label=provider,
            kind="platform",
            capabilities=_openai_compatible_provider_capabilities(provider),
        )
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    ),
    PlatformProviderSpec(
        provider=PROVIDER_LITSERVE,
        label=HUMANITEC_MODELS_DISPLAY_LABEL,
        kind="platform",
        capabilities=frozenset({AICapability.EMBEDDING, AICapability.RERANK}),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider=PROVIDER_LITSERVE_CRAWL,
        label=HUMANITEC_MODELS_DISPLAY_LABEL,
        kind="platform",
        capabilities=frozenset({AICapability.LLM_CHAT}),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider=VOICE_PROVIDER_LITSERVE,
        label=HUMANITEC_VOICE_DISPLAY_LABEL,
        kind="platform",
        capabilities=frozenset(VOICE_CAPABILITIES),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider="cloud_ru",
        label="cloud_ru",
        kind="platform",
        capabilities=frozenset({AICapability.VOICE_STT, AICapability.VOICE_TTS}),
    ),
    PlatformProviderSpec(
        provider="yandex",
        label="yandex",
        kind="platform",
        capabilities=frozenset({AICapability.VOICE_STT, AICapability.VOICE_TTS}),
    ),
    PlatformProviderSpec(
        provider="sber",
        label="sber",
        kind="platform",
        capabilities=frozenset({AICapability.VOICE_STT, AICapability.VOICE_TTS}),
    ),
)

_PLATFORM_PROVIDER_BY_SLUG: dict[str, PlatformProviderSpec] = {
    spec.provider: spec for spec in PLATFORM_PROVIDER_SPECS
}
PLATFORM_AI_PROVIDER_ORDER: tuple[str, ...] = tuple(spec.provider for spec in PLATFORM_PROVIDER_SPECS)
PLATFORM_AI_PROVIDER_SLUGS: frozenset[str] = frozenset(PLATFORM_AI_PROVIDER_ORDER)


def normalize_capability(capability: AICapability | str) -> AICapability:
    if isinstance(capability, AICapability):
        return capability
    return AICapability(capability)


def platform_provider_spec(provider: str) -> PlatformProviderSpec | None:
    return _PLATFORM_PROVIDER_BY_SLUG.get(provider.strip())


def provider_supports_capability(provider: str, capability: AICapability | str) -> bool:
    spec = platform_provider_spec(provider)
    if spec is None:
        return False
    cap = normalize_capability(capability)
    return cap in spec.capabilities


def platform_provider_specs_for_capability(
    capability: AICapability | str,
) -> list[PlatformProviderSpec]:
    cap = normalize_capability(capability)
    return [spec for spec in PLATFORM_PROVIDER_SPECS if cap in spec.capabilities]


def validate_platform_provider_for_capability(provider: str, capability: AICapability | str) -> str:
    slug = provider.strip()
    cap = normalize_capability(capability)
    if not provider_supports_capability(slug, cap):
        allowed = ", ".join(spec.provider for spec in platform_provider_specs_for_capability(cap))
        raise ValueError(
            f"provider {slug!r} не поддерживает capability {cap.value!r}; разрешены: {allowed}"
        )
    return slug


__all__ = [
    "ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS",
    "AICapability",
    "AIProviderKind",
    "EMBEDDING_PROVIDER_ORDER",
    "EMBEDDING_PROVIDER_SLUGS",
    "GITHUB_MODELS_API_VERSION",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "HUMANITEC_LLMS_DISPLAY_LABEL",
    "HUMANITEC_MODELS_DISPLAY_LABEL",
    "HUMANITEC_VOICE_DISPLAY_LABEL",
    "LLM_CAPABILITIES",
    "LLM_CAPABILITY_VALUES",
    "LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER",
    "LLM_PROVIDER_DEFAULT_BASE_URLS",
    "LLM_PROVIDER_DEFAULT_MODELS_URLS",
    "LLM_PROVIDER_DETECTION_HOSTS",
    "LLM_PROVIDER_SMOKE_MODELS",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER",
    "OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS",
    "PLATFORM_AI_PROVIDER_ORDER",
    "PLATFORM_AI_PROVIDER_SLUGS",
    "PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS",
    "PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER",
    "PLATFORM_LLM_PROVIDER_ORDER",
    "PLATFORM_LLM_PROVIDER_SLUGS",
    "PLATFORM_PROVIDER_SPECS",
    "PROVIDER_LITSERVE",
    "PROVIDER_LITSERVE_CRAWL",
    "PlatformProviderSpec",
    "RERANK_PROVIDER_ORDER",
    "RERANK_PROVIDER_SLUGS",
    "VOICE_CAPABILITIES",
    "VOICE_CAPABILITY_VALUES",
    "VOICE_PROVIDER_LITSERVE",
    "ZERO_PRICE_LLM_PROVIDER_SLUGS",
    "humanitec_llms_model_ref",
    "normalize_capability",
    "platform_provider_spec",
    "platform_provider_specs_for_capability",
    "provider_supports_capability",
    "split_humanitec_llms_model_ref",
    "split_provider_prefixed_model",
    "validate_platform_provider_for_capability",
]
