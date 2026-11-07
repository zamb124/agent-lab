"""
RAG-провайдер из Pydantic ``BaseSettings``: выбор ключа, ``model_dump`` записи,
эмбеддинги для pgvector (с учётом per-company override), инстанцирование класса провайдера.

CleanFirst: легаси singleton ``_default_rag_provider`` / ``get_default_rag_provider`` /
``reset_default_rag_provider_cache`` удалены — везде используется ``get_rag_provider(...)``
напрямую с per-request кэшем по содержимому bundle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.ai.company_settings.schema import CUSTOM_PROVIDER_SLUG
from core.ai.models import ResolvedAIModel
from core.ai.providers import PROVIDER_LITSERVE, AICapability
from core.ai.resolver import resolve_ai_model
from core.billing.service import BillingService
from core.config.base import BaseSettings, get_settings
from core.config.models import RAGProviderConfig
from core.config.openai_v1_base_url import openai_v1_base_url
from core.context import get_context
from core.logging import get_logger
from core.rag.embedding_runtime import RagEmbeddingRuntime, resolve_rag_embedding_runtime
from core.rag.providers.agentset_provider import AgentsetRAGProvider
from core.rag.providers.pgvector_provider import PgVectorProvider
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.rag.base_provider import BaseRAGProvider

logger = get_logger(__name__)
_providers_cache: dict[str, type["BaseRAGProvider"]] | None = None
_provider_instances_cache: dict[str, "BaseRAGProvider"] = {}


def _providers() -> dict[str, type["BaseRAGProvider"]]:
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = {
            "agentset": AgentsetRAGProvider,
            "pgvector": PgVectorProvider,
        }
    return _providers_cache


def __getattr__(name: str) -> dict[str, type["BaseRAGProvider"]]:
    if name == "RAG_PROVIDERS":
        return _providers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True)
class ResolvedRagProvider:
    """Ключ провайдера, ``model_dump`` провайдера и runtime эмбеддингов (только ``pgvector``)."""

    provider_key: str
    provider_config: RAGProviderConfig
    embedding_runtime: RagEmbeddingRuntime | None


def _runtime_from_company_embedding(
    resolved: ResolvedAIModel,
    *,
    settings: BaseSettings,
) -> RagEmbeddingRuntime:
    if resolved.model is None or not resolved.model.strip():
        raise ValueError('company embedding override: model is required')
    if resolved.dimension is None:
        raise ValueError('company embedding override: dimension is required')
    if resolved.provider is None or not resolved.provider.strip():
        raise ValueError('company embedding override: provider is required')
    provider = resolved.provider
    if provider == PROVIDER_LITSERVE:
        base_url = (
            resolved.base_url.strip()
            if resolved.base_url is not None and resolved.base_url.strip()
            else openai_v1_base_url(
                settings.server.get_service_url("provider_litserve")
            )
        )
    elif provider == CUSTOM_PROVIDER_SLUG:
        base_url = (resolved.base_url or "").strip()
        if not base_url:
            raise ValueError('company custom embedding override: base_url is required')
    else:
        base_url = (resolved.base_url or "").strip()
        if not base_url:
            emb_copy = settings.rag.embedding.model_copy(
                deep=True,
                update={"provider": provider},
            )
            base_url = resolve_rag_embedding_runtime(
                emb_copy,
                settings.llm,
                _litserve_v1_base_url(settings),
            ).base_url
    return RagEmbeddingRuntime(
        provider=provider,
        model=resolved.model,
        dimension=resolved.dimension,
        base_url=base_url,
        mrl_output_dimension=resolved.mrl_output_dimension,
        extra_request_headers={key: str(value) for key, value in resolved.headers.items()} or None,
        query_instruction=settings.rag.embedding.api.query_instruction,
    )


def _litserve_v1_base_url(settings: BaseSettings) -> str:
    """Канонический OpenAI-корень provider_litserve: ``server.get_service_url`` + ``/v1``."""
    return openai_v1_base_url(settings.server.get_service_url("provider_litserve"))


def resolve_rag_provider_bundle(
    settings: BaseSettings,
    provider_name: str | None = None,
) -> ResolvedRagProvider:
    rag = settings.rag
    key = rag.get_enabled_provider_key(provider_name)
    provider_config = rag.providers[key]
    embedding_runtime: RagEmbeddingRuntime | None = None
    if key == "pgvector":
        llm = settings.llm
        emb = rag.embedding
        if provider_name is None:
            ctx = get_context()
            if ctx is not None and ctx.active_company is not None:
                resolved = resolve_ai_model(
                    AICapability.EMBEDDING,
                    include_platform_default=False,
                )
                if resolved is not None:
                    provider_config = provider_config.model_copy(
                        update=(
                            {"embedding_api_key": resolved.api_key}
                            if resolved.api_key
                            else {}
                        )
                    )
                    embedding_runtime = _runtime_from_company_embedding(resolved, settings=settings)

        if embedding_runtime is None:
            embedding_runtime = resolve_rag_embedding_runtime(
                emb,
                llm,
                _litserve_v1_base_url(settings),
            )
    return ResolvedRagProvider(
        provider_key=key,
        provider_config=provider_config,
        embedding_runtime=embedding_runtime,
    )


def _bundle_cache_key(bundle: ResolvedRagProvider) -> str:
    embedding_runtime_payload: JsonObject | None = None
    if bundle.embedding_runtime is not None:
        embedding_runtime_payload = {
            "provider": bundle.embedding_runtime.provider,
            "model": bundle.embedding_runtime.model,
            "dimension": bundle.embedding_runtime.dimension,
            "base_url": bundle.embedding_runtime.base_url,
            "mrl_output_dimension": bundle.embedding_runtime.mrl_output_dimension,
            "extra_request_headers": bundle.embedding_runtime.extra_request_headers,
            "query_instruction": bundle.embedding_runtime.query_instruction,
        }
    payload: JsonObject = {
        "provider_key": bundle.provider_key,
        "provider_config": require_json_object(
            bundle.provider_config.model_dump(mode="json"),
            "RAG provider config",
        ),
        "embedding_runtime": embedding_runtime_payload,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def get_rag_provider(
    provider_name: str | None = None,
    *,
    settings: BaseSettings | None = None,
    billing_service: BillingService,
) -> "BaseRAGProvider":
    """
    Создаёт RAG провайдер из ``get_settings()``: активный ключ, ``RAGProviderConfig.model_dump()``,
    для ``pgvector`` — embedding runtime с учётом per-company override.

    Кэш — по полному содержимому bundle (включая компанейский embedding override),
    чтобы разные компании получали разные инстансы автоматически.
    """
    active_settings = settings or get_settings()
    bundle = resolve_rag_provider_bundle(active_settings, provider_name)
    cache_key = _bundle_cache_key(bundle)
    cached = _provider_instances_cache.get(cache_key)
    if cached is not None:
        return cached
    registry = _providers()

    if bundle.provider_key not in registry:
        available = ", ".join(sorted(registry.keys()))
        raise ValueError(
            f"RAG provider {bundle.provider_key!r} is not registered in the factory. Available: {available}"
        )

    provider_class = registry[bundle.provider_key]
    if bundle.provider_key == "pgvector":
        instance = PgVectorProvider(
            bundle.provider_config,
            embedding_runtime=bundle.embedding_runtime,
            billing_service=billing_service,
        )
    else:
        instance = provider_class(bundle.provider_config)

    _provider_instances_cache[cache_key] = instance
    logger.info("config.rag", provider_key=bundle.provider_key)
    return instance


def reset_rag_provider_instances_cache() -> None:
    """Сброс кэша инстансов провайдеров (используется в тестах при смене settings)."""
    _provider_instances_cache.clear()


__all__ = [
    "ResolvedRagProvider",
    "get_rag_provider",
    "reset_rag_provider_instances_cache",
    "resolve_rag_provider_bundle",
]
