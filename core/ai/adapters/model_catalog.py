from __future__ import annotations

from core.ai.adapters.base import AIProviderAdapter
from core.ai.adapters.huggingface import HuggingFaceModelCatalogAdapter
from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.adapters.openrouter import OpenRouterModelCatalogAdapter
from core.ai.adapters.provider_litserve import ProviderLitserveModelCatalogAdapter
from core.ai.adapters.provider_litserve_crawl import ProviderLitserveCrawlModelCatalogAdapter
from core.ai.adapters.registry import AIProviderAdapterRegistry
from core.ai.providers import OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
from core.config import BaseSettings, get_settings


def create_model_catalog_adapter_registry(
    settings: BaseSettings | None = None,
) -> AIProviderAdapterRegistry:
    resolved_settings = settings or get_settings()
    special_adapters: tuple[AIProviderAdapter, ...] = (
        OpenRouterModelCatalogAdapter(resolved_settings),
        HuggingFaceModelCatalogAdapter(resolved_settings),
    )
    special_providers = frozenset(adapter.provider for adapter in special_adapters)
    adapters: list[AIProviderAdapter] = [*special_adapters]
    adapters.extend(
        OpenAICompatibleModelCatalogAdapter(provider, resolved_settings)
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
        if provider not in special_providers
    )
    adapters.append(ProviderLitserveModelCatalogAdapter(resolved_settings))
    adapters.append(ProviderLitserveCrawlModelCatalogAdapter(resolved_settings))
    return AIProviderAdapterRegistry(adapters)


__all__ = ["create_model_catalog_adapter_registry"]
