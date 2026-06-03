"""Canonical AI platform layer.

Provider/capability catalog is exposed from this package. Keep this package
initializer lightweight: ``core.config`` imports ``core.ai.providers`` during
settings model construction, so resolver/runtime entrypoints live in explicit
modules ``core.ai.resolver`` and ``core.ai.runtime``.
"""

from core.ai.providers import (
    EMBEDDING_PROVIDER_ORDER,
    LLM_CAPABILITIES,
    PROVIDER_LITSERVE,
    RERANK_PROVIDER_ORDER,
    VOICE_CAPABILITIES,
    AICapability,
    PlatformProviderSpec,
    platform_provider_specs_for_capability,
    provider_supports_capability,
    validate_platform_provider_for_capability,
)

__all__ = [
    "AICapability",
    "EMBEDDING_PROVIDER_ORDER",
    "LLM_CAPABILITIES",
    "PROVIDER_LITSERVE",
    "PlatformProviderSpec",
    "RERANK_PROVIDER_ORDER",
    "VOICE_CAPABILITIES",
    "platform_provider_specs_for_capability",
    "provider_supports_capability",
    "validate_platform_provider_for_capability",
]
