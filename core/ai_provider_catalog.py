"""Canonical AI provider/capability catalog for platform, company settings and RAG.

The catalog is intentionally independent from ``core.company_ai.schema`` to avoid
cycles: Pydantic schemas, frontend settings API and runtime resolvers all import
this module as the single source of provider/capability truth.

This module does not contain provider model ids. Models are dynamic data from
the existing provider model catalog, populated by provider discovery/probes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from core.llm_model_routing import (
    HUMANITEC_LLM_PROVIDER,
    HUMANITEC_LLMS_DISPLAY_LABEL,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
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


AIProviderKind = Literal["virtual", "platform", "policy"]

PROVIDER_LITSERVE = "provider_litserve"
VOICE_PROVIDER_LITSERVE = "litserve"
RERANK_POLICY_INHERIT = "inherit"
RERANK_POLICY_NONE = "none"

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


@dataclass(frozen=True)
class PlatformProviderSpec:
    provider: str
    label: str
    kind: AIProviderKind
    capabilities: frozenset[AICapability]
    byok_allowed: bool = True


_OPENAI_COMPATIBLE_LLM_CAPABILITIES = frozenset(LLM_CAPABILITIES)

OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ORDER: tuple[str, ...] = (
    "openai",
    "bothub",
    "google",
    "deepinfra",
)
OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_SLUGS: frozenset[str] = frozenset(
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_ORDER
)

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
            capabilities=(
                frozenset({*_OPENAI_COMPATIBLE_LLM_CAPABILITIES, AICapability.EMBEDDING})
                if provider in OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_SLUGS
                else _OPENAI_COMPATIBLE_LLM_CAPABILITIES
            ),
        )
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    ),
    PlatformProviderSpec(
        provider=PROVIDER_LITSERVE,
        label=PROVIDER_LITSERVE,
        kind="platform",
        capabilities=frozenset({AICapability.EMBEDDING, AICapability.RERANK}),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider=VOICE_PROVIDER_LITSERVE,
        label=VOICE_PROVIDER_LITSERVE,
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
    PlatformProviderSpec(
        provider="silero_local",
        label="silero_local",
        kind="platform",
        capabilities=frozenset({AICapability.VOICE_VAD}),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider="mock",
        label="mock",
        kind="platform",
        capabilities=frozenset(VOICE_CAPABILITIES),
        byok_allowed=False,
    ),
)

_PLATFORM_PROVIDER_BY_SLUG: dict[str, PlatformProviderSpec] = {
    spec.provider: spec for spec in PLATFORM_PROVIDER_SPECS
}
PLATFORM_AI_PROVIDER_ORDER: tuple[str, ...] = tuple(spec.provider for spec in PLATFORM_PROVIDER_SPECS)
PLATFORM_AI_PROVIDER_SLUGS: frozenset[str] = frozenset(PLATFORM_AI_PROVIDER_ORDER)

RERANK_POLICY_SPECS: tuple[PlatformProviderSpec, ...] = (
    PlatformProviderSpec(
        provider=RERANK_POLICY_INHERIT,
        label=RERANK_POLICY_INHERIT,
        kind="policy",
        capabilities=frozenset({AICapability.RERANK}),
        byok_allowed=False,
    ),
    PlatformProviderSpec(
        provider=RERANK_POLICY_NONE,
        label=RERANK_POLICY_NONE,
        kind="policy",
        capabilities=frozenset({AICapability.RERANK}),
        byok_allowed=False,
    ),
)

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
    *,
    include_policies: bool = False,
) -> list[PlatformProviderSpec]:
    cap = normalize_capability(capability)
    specs = [spec for spec in PLATFORM_PROVIDER_SPECS if cap in spec.capabilities]
    if include_policies and cap == AICapability.RERANK:
        specs = [*RERANK_POLICY_SPECS, *specs]
    return specs


def validate_platform_provider_for_capability(provider: str, capability: AICapability | str) -> str:
    slug = provider.strip()
    cap = normalize_capability(capability)
    if not provider_supports_capability(slug, cap):
        allowed = ", ".join(spec.provider for spec in platform_provider_specs_for_capability(cap))
        raise ValueError(
            f"provider {slug!r} не поддерживает capability {cap.value!r}; разрешены: {allowed}"
        )
    return slug
