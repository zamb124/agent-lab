"""
Стабильный импорт ``core.rag.factory``; реализация в ``core.config.rag_provider_factory``.
"""

from core.config.rag_provider_factory import (
    RAG_PROVIDERS,
    ResolvedRagProvider,
    get_default_rag_provider,
    get_rag_provider,
    resolve_rag_provider_bundle,
)

__all__ = [
    "RAG_PROVIDERS",
    "ResolvedRagProvider",
    "get_default_rag_provider",
    "get_rag_provider",
    "resolve_rag_provider_bundle",
]
