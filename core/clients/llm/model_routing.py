"""
Маршрутизация LLM: префикс платформенного провайдера в поле model.

Формат: ``<slug>:<model_id>`` (первое вхождение ``:``), где ``slug`` —
``openrouter``, ``openai``, ``bothub``, ``provider_litserve``, ``yandex``,
``humanitec_llm``.
Идентификаторы вида ``vendor/model`` без такого префикса не изменяются.
"""

from __future__ import annotations

from typing import Optional

HUMANITEC_LLM_PROVIDER = "humanitec_llm"
HUMANITEC_LLM_AUTO_MODEL = "auto"

LLM_ROUTING_PROVIDER_SLUGS = frozenset(
    {
        "openrouter",
        "openai",
        "bothub",
        "provider_litserve",
        "yandex",
        "custom_openai_compatible",
        HUMANITEC_LLM_PROVIDER,
    }
)


def _provider_field_set(provider: Optional[str]) -> bool:
    return provider is not None and str(provider).strip() != ""


def split_provider_prefixed_model(
    provider: Optional[str], model: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """
    Если ``provider`` не задан, а ``model`` вида ``openrouter:openai/gpt-4o``,
    возвращает ``(openrouter, openai/gpt-4o)``. Иначе ``(provider, model)`` без изменений
    (кроме случая «провайдер не задан и split не применён» → ``(None, model)``).
    """
    if _provider_field_set(provider):
        return provider, model
    if not model or not isinstance(model, str):
        return None, model
    if ":" not in model:
        return None, model
    provider_prefix, _, model_without_provider_prefix = model.partition(":")
    if not provider_prefix or not model_without_provider_prefix:
        return None, model
    if provider_prefix not in LLM_ROUTING_PROVIDER_SLUGS:
        return None, model
    return provider_prefix, model_without_provider_prefix
