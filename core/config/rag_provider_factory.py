"""
RAG-провайдер из Pydantic ``BaseSettings``: выбор ключа, ``model_dump`` записи, эмбеддинги для pgvector, инстанцирование класса провайдера.

Импорты из ``core.rag.providers`` / ``core.rag.embedding_runtime`` только внутри функций,
чтобы не зациклиться с ``core.rag.__init__``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from core.config.base import BaseSettings, get_settings

if TYPE_CHECKING:
    from core.rag.base_provider import BaseRAGProvider

logger = logging.getLogger(__name__)

_providers_cache: dict[str, type[Any]] | None = None


def _providers() -> dict[str, type[Any]]:
    global _providers_cache
    if _providers_cache is None:
        from core.rag.providers.agentset_provider import AgentsetRAGProvider
        from core.rag.providers.pgvector_provider import PgVectorProvider

        _providers_cache = {
            "agentset": AgentsetRAGProvider,
            "pgvector": PgVectorProvider,
        }
    return _providers_cache


def __getattr__(name: str) -> Any:
    if name == "RAG_PROVIDERS":
        return _providers()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass(frozen=True)
class ResolvedRagProvider:
    """Ключ провайдера, ``model_dump`` провайдера и runtime эмбеддингов (только ``pgvector``)."""

    provider_key: str
    provider_config: dict[str, Any]
    embedding_runtime: Any | None


def resolve_rag_provider_bundle(
    settings: BaseSettings,
    provider_name: Optional[str] = None,
) -> ResolvedRagProvider:
    from core.rag.embedding_runtime import resolve_rag_embedding_runtime

    rag = settings.rag
    key = rag.get_enabled_provider_key(provider_name)
    provider_config = rag.providers[key].model_dump()
    embedding_runtime: Any | None = None
    if key == "pgvector":
        embedding_runtime = resolve_rag_embedding_runtime(
            rag.embedding,
            settings.llm,
            settings.provider_litserve,
        )
    return ResolvedRagProvider(
        provider_key=key,
        provider_config=provider_config,
        embedding_runtime=embedding_runtime,
    )


def get_rag_provider(provider_name: Optional[str] = None) -> BaseRAGProvider:
    """
    Создаёт RAG провайдер из ``get_settings()``: активный ключ, ``RAGProviderConfig.model_dump()``,
    для ``pgvector`` — ``resolve_rag_embedding_runtime(rag.embedding, llm, provider_litserve)``.
    """
    settings = get_settings()
    bundle = resolve_rag_provider_bundle(settings, provider_name)
    registry = _providers()

    if bundle.provider_key not in registry:
        available = ", ".join(sorted(registry.keys()))
        raise ValueError(
            f"RAG провайдер {bundle.provider_key!r} не зарегистрирован в фабрике. Доступные: {available}"
        )

    provider_class = registry[bundle.provider_key]
    if bundle.provider_key == "pgvector":
        instance = provider_class(
            bundle.provider_config,
            embedding_config=bundle.embedding_runtime,
        )
    else:
        instance = provider_class(bundle.provider_config)

    logger.info("Создан RAG провайдер: %s", bundle.provider_key)
    return instance


_default_rag_provider: Optional[BaseRAGProvider] = None


def reset_default_rag_provider_cache() -> None:
    """Сброс синглтона провайдера после смены глобальных настроек (например ``set_settings``)."""
    global _default_rag_provider
    _default_rag_provider = None


def get_default_rag_provider() -> BaseRAGProvider:
    """Дефолтный RAG провайдер (синглтон на процесс)."""
    global _default_rag_provider

    if _default_rag_provider is None:
        _default_rag_provider = get_rag_provider()

    return _default_rag_provider


__all__ = [
    "RAG_PROVIDERS",
    "ResolvedRagProvider",
    "reset_default_rag_provider_cache",
    "get_default_rag_provider",
    "get_rag_provider",
    "resolve_rag_provider_bundle",
]
