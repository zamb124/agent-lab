"""
Платформенные дефолтные модели по capability и (provider, capability).

Используется резолвером, когда у компании задан только провайдер и нужно подставить модель,
для capability с фиксированной платформенной моделью (LLM_SUMMARIZE, LLM_FORMAT_MARKDOWN,
LLM_CODEGEN, LLM_VISION, IMAGE_GEN). Для LLM_CHAT модель берётся из bundle/нodes flows
(резолвер не подменяет).

Модели задаются на уровне платформы — компания их не редактирует.
"""

from __future__ import annotations

from core.company_ai.schema import AICapability
from core.config import get_settings

# Дефолтная модель на capability при отсутствии provider-специфической записи.
# Если ключа capability нет — резолвер возьмёт settings.llm.default_model (LLM_CHAT/CODEGEN)
# либо упадёт ValueError для строгих capability (LLM_VISION, IMAGE_GEN, LLM_FORMAT_MARKDOWN).
_PLATFORM_FALLBACK_MODEL_BY_CAPABILITY: dict[AICapability, str | None] = {
    AICapability.LLM_CHAT: None,  # из settings.llm.default_model
    AICapability.LLM_SUMMARIZE: "qwen/qwen3.5-397b-a17b",
    AICapability.LLM_FORMAT_MARKDOWN: None,  # резолвится через provider_litserve.infra.markdown_default_api_model_id
    AICapability.LLM_CODEGEN: None,  # из settings.llm.default_model
    AICapability.LLM_VISION: "google/gemini-2.5-flash-preview",
    AICapability.IMAGE_GEN: "google/nano-banana",
}


# Per-(provider, capability) модель — когда платформа умеет жёстко смаппить
# provider компании в конкретную модель.
_PROVIDER_MODEL_BY_CAPABILITY: dict[AICapability, dict[str, str]] = {
    AICapability.LLM_SUMMARIZE: {
        "openrouter": "qwen/qwen3.5-397b-a17b",
        "provider_litserve": "Qwen/Qwen2.5-1.5B-Instruct",
        "bothub": "openai/gpt-4o-mini",
        "yandex": "yandexgpt/latest",
    },
    AICapability.LLM_VISION: {
        "openrouter": "google/gemini-2.5-flash-preview",
        "openai": "gpt-4o",
        "yandex": "yandexgpt/latest",
    },
    AICapability.IMAGE_GEN: {
        "openrouter": "google/nano-banana",
    },
}


def platform_default_model(capability: AICapability, provider: str | None = None) -> str | None:
    """Платформенная модель для capability и (опц.) провайдера.

    Возвращает None, если для capability нет жёсткого дефолта (например LLM_CHAT — берётся
    из settings.llm.default_model, или из bundle-нод flows runtime overlay-ом).
    """
    if provider:
        per_provider = _PROVIDER_MODEL_BY_CAPABILITY.get(capability) or {}
        if provider in per_provider and str(per_provider[provider]).strip():
            return str(per_provider[provider]).strip()
    fallback = _PLATFORM_FALLBACK_MODEL_BY_CAPABILITY.get(capability)
    if fallback is not None and str(fallback).strip():
        return str(fallback).strip()

    if capability in (AICapability.LLM_CHAT, AICapability.LLM_CODEGEN):
        s = get_settings()
        m = s.llm.default_model
        return str(m).strip() if m else None
    if capability == AICapability.LLM_FORMAT_MARKDOWN:
        s = get_settings()
        infra_model = (s.provider_litserve.infra.markdown_default_api_model_id or "").strip()
        if infra_model:
            return infra_model
        return (s.provider_litserve.infra.llm_model_id or "").strip() or None
    return None


def platform_default_provider_for_capability(capability: AICapability) -> str:
    """Платформенный провайдер по умолчанию для capability (без company override).

    Внимание: capability могут иметь собственный платформенный путь,
    отличный от ``settings.llm.provider``. Например ``LLM_FORMAT_MARKDOWN``
    по умолчанию идёт через LitServe ``POST /v1/text/format_markdown``
    (см. ``core.text_transforms.routing.should_use_litserve_format_markdown_http``
    и ``apps/crm_worker/tasks/note_markdown_tasks.py``), поэтому платформенный
    провайдер для этой capability — ``provider_litserve``, а не общий
    ``settings.llm.provider``.
    """
    s = get_settings()
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
    if capability == AICapability.LLM_FORMAT_MARKDOWN:
        return "provider_litserve"
    return s.llm.provider


__all__ = [
    "platform_default_model",
    "platform_default_provider_for_capability",
]
