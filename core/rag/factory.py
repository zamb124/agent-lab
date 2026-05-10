"""
Стабильный импорт ``core.rag.factory``; реализация в ``core.config.rag_provider_factory``.
"""

from core.config.rag_provider_factory import (
    RAG_PROVIDERS,
    ResolvedRagProvider,
    get_rag_provider,
    reset_rag_provider_instances_cache,
    resolve_rag_provider_bundle,
)

__all__ = [
    "RAG_PROVIDERS",
    "ResolvedRagProvider",
    "get_rag_provider",
    "reset_rag_provider_instances_cache",
    "resolve_rag_provider_bundle",
]
