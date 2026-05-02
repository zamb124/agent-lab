"""
RAG-провайдер из Pydantic ``BaseSettings``: выбор ключа, ``model_dump`` записи, эмбеддинги для pgvector, инстанцирование класса провайдера.

Импорты из ``core.rag.providers`` / ``core.rag.embedding_runtime`` только внутри функций,
чтобы не зациклиться с ``core.rag.__init__``.
"""

from __future__ import annotations

import json

from core.logging import get_logger
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Any, Optional

from core.config.base import BaseSettings, get_settings
from core.context import get_context

if TYPE_CHECKING:
    from core.rag.base_provider import BaseRAGProvider

logger = get_logger(__name__)
_providers_cache: dict[str, type[Any]] | None = None
_provider_instances_cache: dict[str, Any] = {}
_RAG_EMBEDDING_OVERRIDE_KEY = "rag_embedding_override"
_RAG_EMBEDDING_ALLOWED_PROVIDERS = {"openrouter", "provider_litserve"}

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
    rag = settings.rag
    key = rag.get_enabled_provider_key(provider_name)
    provider_config = dict(rag.providers[key].model_dump())
    embedding_runtime: Any | None = None
    if key == "pgvector":
        api = rag.embedding.api
        embedding_runtime = {
            "provider": rag.embedding.provider,
            "model": api.model,
            "dimension": api.dimension,
            "base_url": api.base_url,
            "mrl_output_dimension": api.mrl_output_dimension,
        }
        if provider_name is None:
            override = _resolve_company_rag_embedding_override()
            if override is not None:
                embedding_override = rag.embedding.model_copy(deep=True)
                embedding_override.provider = override["provider"]
                embedding_override.api.model = override["model"]
                api2 = embedding_override.api
                embedding_runtime = {
                    "provider": embedding_override.provider,
                    "model": api2.model,
                    "dimension": api2.dimension,
                    "base_url": api2.base_url,
                    "mrl_output_dimension": api2.mrl_output_dimension,
                }
    return ResolvedRagProvider(
        provider_key=key,
        provider_config=provider_config,
        embedding_runtime=embedding_runtime,
    )

def _resolve_company_rag_embedding_override() -> dict[str, str] | None:
    context = get_context()
    if context is None or context.active_company is None:
        return None
    metadata = context.active_company.metadata
    raw = metadata.get(_RAG_EMBEDDING_OVERRIDE_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("company.metadata.rag_embedding_override должен быть объектом")
    provider_raw = raw.get("provider")
    model_raw = raw.get("model")
    if not isinstance(provider_raw, str) or provider_raw not in _RAG_EMBEDDING_ALLOWED_PROVIDERS:
        raise ValueError("company.metadata.rag_embedding_override.provider имеет недопустимое значение")
    if not isinstance(model_raw, str) or not model_raw.strip():
        raise ValueError("company.metadata.rag_embedding_override.model должен быть непустой строкой")
    return {"provider": provider_raw, "model": model_raw.strip()}

def _bundle_cache_key(bundle: ResolvedRagProvider) -> str:
    embedding_runtime: Any = bundle.embedding_runtime
    if embedding_runtime is not None and is_dataclass(embedding_runtime):
        embedding_runtime = asdict(embedding_runtime)
    payload = {
        "provider_key": bundle.provider_key,
        "provider_config": bundle.provider_config,
        "embedding_runtime": embedding_runtime,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)

def get_rag_provider(
    provider_name: Optional[str] = None,
    *,
    settings: BaseSettings | None = None,
) -> BaseRAGProvider:
    """
    Создаёт RAG провайдер из ``get_settings()``: активный ключ, ``RAGProviderConfig.model_dump()``,
    для ``pgvector`` — ``resolve_rag_embedding_runtime(rag.embedding, llm, provider_litserve)``.
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
        instance = provider_class(
            bundle.provider_config,
            embedding_config=bundle.embedding_runtime,
        )
    else:
        instance = provider_class(bundle.provider_config)

    _provider_instances_cache[cache_key] = instance
    logger.info("Создан RAG провайдер: %s", bundle.provider_key)
    return instance

_default_rag_provider: Optional[BaseRAGProvider] = None

def reset_default_rag_provider_cache() -> None:
    """Сброс синглтона провайдера после смены глобальных настроек (например ``set_settings``)."""
    global _default_rag_provider
    _default_rag_provider = None
    _provider_instances_cache.clear()

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
