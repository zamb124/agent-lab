"""Платформенный default-route для AI capabilities."""

from __future__ import annotations

from core.ai.providers import AICapability
from core.clients.llm.model_routing import HUMANITEC_LLM_AUTO_MODEL, HUMANITEC_LLM_PROVIDER
from core.config import get_settings

_LLM_CAPABILITIES: frozenset[AICapability] = frozenset(
    {
        AICapability.LLM_CHAT,
        AICapability.LLM_SUMMARIZE,
        AICapability.LLM_FORMAT_MARKDOWN,
        AICapability.LLM_CODEGEN,
        AICapability.LLM_VISION,
        AICapability.IMAGE_GEN,
    }
)


def platform_default_model(capability: AICapability, provider: str | None = None) -> str | None:
    """Платформенная модель по умолчанию без provider-specific hardcode."""
    if capability in _LLM_CAPABILITIES and provider in (None, HUMANITEC_LLM_PROVIDER):
        return HUMANITEC_LLM_AUTO_MODEL
    return None


def platform_default_provider_for_capability(capability: AICapability) -> str:
    """Платформенный провайдер по умолчанию для capability без company override."""
    s = get_settings()
    if capability in _LLM_CAPABILITIES:
        return HUMANITEC_LLM_PROVIDER
    if capability == AICapability.EMBEDDING:
        return s.rag.embedding.provider
    if capability == AICapability.RERANK:
        return s.rag.reranker.provider
    if capability == AICapability.VOICE_STT:
        return s.voice.stt.provider
    if capability == AICapability.VOICE_TTS:
        return s.voice.tts.provider
    if capability == AICapability.VOICE_VAD:
        return s.voice.vad.provider
    return s.llm.provider


__all__ = [
    "platform_default_model",
    "platform_default_provider_for_capability",
]
