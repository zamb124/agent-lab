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
from typing import TYPE_CHECKING, Literal

from core.company_ai.resolver import resolve_embedding_for_company
from core.config.base import BaseSettings, get_settings
from core.config.models import RAGProviderConfig
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
        pls = settings.provider_litserve
        emb = rag.embedding
        if provider_name is None:
            ctx = get_context()
            if ctx is not None and ctx.active_company is not None:
                resolved = resolve_embedding_for_company()
                if resolved is not None:
                    if resolved.provider == "provider_litserve":
                        provider: Literal["provider_litserve", "openrouter"] = "provider_litserve"
                    elif resolved.provider == "openrouter":
                        provider = "openrouter"
                    else:
                        raise ValueError(
                            f"embedding provider {resolved.provider!r} не поддерживается RAG pgvector"
                        )
                    emb_copy = rag.embedding.model_copy(deep=True, update={"provider": provider})
                    if resolved.base_url:
                        emb_copy.api.base_url = resolved.base_url
                    emb = emb_copy

        embedding_runtime = resolve_rag_embedding_runtime(emb, llm, pls)
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
            f"RAG провайдер {bundle.provider_key!r} не зарегистрирован в фабрике. Доступные: {available}"
        )

    provider_class = registry[bundle.provider_key]
    if bundle.provider_key == "pgvector":
        instance = PgVectorProvider(
            bundle.provider_config,
            embedding_runtime=bundle.embedding_runtime,
        )
    else:
        instance = provider_class(bundle.provider_config)

    _provider_instances_cache[cache_key] = instance
    logger.info("Создан RAG провайдер: %s", bundle.provider_key)
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
