"""Canonical company-aware AI capability resolver."""

from __future__ import annotations

from typing import TypeAlias

from core.ai.providers import AICapability
from core.company_ai.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    CostOrigin,
    ResolvedEmbedding,
    ResolvedLLM,
    ResolvedRerank,
    ResolvedVoice,
    load_company_ai_providers,
    resolve_custom_llm_provider_ref,
    resolve_embedding_for_company,
    resolve_llm_for_capability,
    resolve_rerank_for_company,
    resolve_voice_for_company,
)

ResolvedAIModel: TypeAlias = ResolvedLLM | ResolvedEmbedding | ResolvedRerank | ResolvedVoice


def resolve_ai_for_capability(
    capability: AICapability,
    *,
    include_platform_default: bool = False,
) -> ResolvedAIModel | None:
    """Resolve any platform AI capability through a single typed entrypoint."""
    if capability in {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }:
        return resolve_llm_for_capability(
            capability,
            include_platform_default=include_platform_default,
        )
    if capability == AICapability.EMBEDDING:
        return resolve_embedding_for_company()
    if capability == AICapability.RERANK:
        return resolve_rerank_for_company()
    if capability in (AICapability.VOICE_STT, AICapability.VOICE_TTS, AICapability.VOICE_VAD):
        return resolve_voice_for_company(capability)
    raise ValueError(f"resolve_ai_for_capability: неизвестная capability {capability!r}")


__all__ = [
    "COST_ORIGIN_COMPANY",
    "COST_ORIGIN_PLATFORM",
    "AICapability",
    "CostOrigin",
    "ResolvedAIModel",
    "ResolvedEmbedding",
    "ResolvedLLM",
    "ResolvedRerank",
    "ResolvedVoice",
    "load_company_ai_providers",
    "resolve_ai_for_capability",
    "resolve_custom_llm_provider_ref",
    "resolve_embedding_for_company",
    "resolve_llm_for_capability",
    "resolve_rerank_for_company",
    "resolve_voice_for_company",
]
