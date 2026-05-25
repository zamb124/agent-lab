"""
LLM model routing constants and parser.

This module is intentionally independent from ``core.clients.llm`` so config
models can import routing defaults without initializing LLM clients.
"""

from __future__ import annotations

HUMANITEC_LLM_PROVIDER = "humanitec_llm"
HUMANITEC_LLM_AUTO_MODEL = "auto"

LLM_ROUTING_PROVIDER_SLUGS = frozenset(
    {
        "openrouter",
        "openai",
        "bothub",
        "yandex",
        "custom_openai_compatible",
        HUMANITEC_LLM_PROVIDER,
    }
)


def _provider_field_set(provider: str | None) -> bool:
    return provider is not None and str(provider).strip() != ""


def split_provider_prefixed_model(
    provider: str | None, model: str | None
) -> tuple[str | None, str | None]:
    if _provider_field_set(provider):
        return provider, model
    if not model:
        return None, model
    if ":" not in model:
        return None, model
    provider_prefix, _, model_without_provider_prefix = model.partition(":")
    if not provider_prefix or not model_without_provider_prefix:
        return None, model
    if provider_prefix not in LLM_ROUTING_PROVIDER_SLUGS:
        return None, model
    return provider_prefix, model_without_provider_prefix
