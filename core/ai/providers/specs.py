"""Provider routing specs for the canonical AI layer.

This module is intentionally free from runtime clients and settings imports.
Config models, UI DTO builders and provider adapters can import it without
initializing LLM transports.
"""

from __future__ import annotations

HUMANITEC_LLM_PROVIDER = "humanitec_llm"
HUMANITEC_LLM_AUTO_MODEL = "auto"
HUMANITEC_LLMS_DISPLAY_LABEL = "Humanitec LLMs"

OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER: tuple[str, ...] = (
    "openrouter",
    "bothub",
    "groq",
    "google",
    "github",
    "huggingface",
    "deepinfra",
    "openai",
    "yandex",
)
OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS = frozenset(OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER)

ZERO_PRICE_LLM_PROVIDER_SLUGS = frozenset({"openrouter", "bothub"})
ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS = frozenset(
    {"groq", "google", "github", "huggingface"}
)
PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS = frozenset(
    {
        *ZERO_PRICE_LLM_PROVIDER_SLUGS,
        *ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    }
)
PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER: tuple[str, ...] = tuple(
    provider
    for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    if provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS
)

PLATFORM_LLM_PROVIDER_ORDER: tuple[str, ...] = (
    HUMANITEC_LLM_PROVIDER,
    *OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
)
PLATFORM_LLM_PROVIDER_SLUGS = frozenset(PLATFORM_LLM_PROVIDER_ORDER)

LLM_ROUTING_PROVIDER_SLUGS = frozenset(
    {
        *PLATFORM_LLM_PROVIDER_SLUGS,
        "custom_openai_compatible",
        "provider_litserve",
    }
)

LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER: dict[str, str] = {
    "openrouter": "zero_price_catalog",
    "bothub": "zero_price_catalog",
    "groq": "account_free_tier",
    "google": "account_free_tier",
    "github": "account_free_tier",
    "huggingface": "account_free_tier",
    "deepinfra": "no_verified_free_policy",
    "openai": "no_verified_free_policy",
    "yandex": "no_verified_free_policy",
}

LLM_PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "bothub": "https://openai.bothub.chat/v1",
    "yandex": "https://llm.api.cloud.yandex.net/v1",
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "github": "https://models.github.ai/inference",
    "huggingface": "https://router.huggingface.co/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}

LLM_PROVIDER_DEFAULT_MODELS_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1/models",
    "bothub": "https://bothub.chat/api/v2/model/list?children=1",
    "openai": "https://api.openai.com/v1/models",
    "yandex": "https://llm.api.cloud.yandex.net/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "github": "https://models.github.ai/catalog/models",
    "huggingface": "https://router.huggingface.co/v1/models",
    "deepinfra": "https://api.deepinfra.com/v1/openai/models",
}

LLM_PROVIDER_SMOKE_MODELS: dict[str, str] = {
    "openrouter": "openrouter/free",
    "bothub": "gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
    "google": "gemini-2.5-flash-lite",
    "github": "openai/gpt-4o-mini",
    "huggingface": "meta-llama/Llama-3.2-1B-Instruct:fastest",
    "deepinfra": "deepseek-ai/DeepSeek-V3",
}

LLM_PROVIDER_DETECTION_HOSTS: dict[str, tuple[str, ...]] = {
    "openrouter": ("openrouter.ai",),
    "bothub": ("bothub.chat", "openai.bothub.chat"),
    "openai": ("api.openai.com",),
    "yandex": ("llm.api.cloud.yandex.net",),
    "groq": ("api.groq.com",),
    "google": ("generativelanguage.googleapis.com",),
    "github": ("models.github.ai",),
    "huggingface": ("router.huggingface.co",),
    "deepinfra": ("api.deepinfra.com",),
}

GITHUB_MODELS_API_VERSION = "2026-03-10"


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


def humanitec_llms_model_ref(provider: str, model_id: str) -> str:
    resolved_provider = provider.strip()
    resolved_model_id = model_id.strip()
    if not resolved_provider or not resolved_model_id:
        raise ValueError("Humanitec LLMs model ref requires provider and model_id")
    if resolved_provider not in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
        raise ValueError(f"Humanitec LLMs model provider is not a free-pool provider: {provider!r}")
    return f"{resolved_provider}:{resolved_model_id}"


def split_humanitec_llms_model_ref(model: str | None) -> tuple[str, str] | None:
    if model is None:
        return None
    raw_model = str(model).strip()
    if not raw_model or raw_model == HUMANITEC_LLM_AUTO_MODEL:
        return None
    provider, separator, model_id = raw_model.partition(":")
    if not separator or not provider.strip() or not model_id.strip():
        return None
    provider = provider.strip()
    if provider not in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
        return None
    return provider, model_id.strip()


__all__ = [
    "ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS",
    "GITHUB_MODELS_API_VERSION",
    "HUMANITEC_LLM_AUTO_MODEL",
    "HUMANITEC_LLM_PROVIDER",
    "HUMANITEC_LLMS_DISPLAY_LABEL",
    "LLM_FREE_MODEL_DISCOVERY_POLICY_BY_PROVIDER",
    "LLM_PROVIDER_DEFAULT_BASE_URLS",
    "LLM_PROVIDER_DEFAULT_MODELS_URLS",
    "LLM_PROVIDER_DETECTION_HOSTS",
    "LLM_PROVIDER_SMOKE_MODELS",
    "LLM_ROUTING_PROVIDER_SLUGS",
    "OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER",
    "OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS",
    "PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS",
    "PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER",
    "PLATFORM_LLM_PROVIDER_ORDER",
    "PLATFORM_LLM_PROVIDER_SLUGS",
    "ZERO_PRICE_LLM_PROVIDER_SLUGS",
    "humanitec_llms_model_ref",
    "split_humanitec_llms_model_ref",
    "split_provider_prefixed_model",
]
