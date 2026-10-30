"""
RAG public contracts.

The package root stays light: provider implementations pull optional media/ML
dependencies and are imported lazily only when a caller asks for them.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING
from typing import cast as type_cast

from core.rag_indexing_schema import (
    IndexProfileConfig,
    IndexProfileLexicalConfig,
    IndexProfileSearchDefaults,
    IndexProfileSplitConfig,
    IndexProfileSplitStrategy,
    RerankerSearchDefaults,
    SearchChannelsDefaults,
)

from .constants import RAG_IN_PROCESS_PROVIDER_ID
from .models import RAGChunk, RAGDocument, RAGNamespace, RAGSearchResult
from .rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    SEARCH_REQUEST_OPTION_KEYS,
    build_namespace_search_json_body,
    build_namespace_search_path,
    filter_search_request_options,
    merge_search_request_options,
)

if TYPE_CHECKING:
    from types import FunctionType, UnionType

    from .base_provider import BaseRAGProvider
    from .chunking import resolve_split_config, split_file_extract, split_plain_text_fixed_tokens
    from .factory import get_rag_provider
    from .post_retrieval_rerank import (
        apply_rerank_after_retrieve_by_score_desc,
        apply_rerank_after_retrieve_grouped_by_score_desc,
    )
    from .providers import AgentsetRAGProvider, PgVectorProvider
    type _LazyExportValue = (
        type[BaseRAGProvider]
        | type[AgentsetRAGProvider]
        | type[PgVectorProvider]
        | FunctionType
        | UnionType
    )

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseRAGProvider": ("core.rag.base_provider", "BaseRAGProvider"),
    "resolve_split_config": ("core.rag.chunking", "resolve_split_config"),
    "split_file_extract": ("core.rag.chunking", "split_file_extract"),
    "split_plain_text_fixed_tokens": ("core.rag.chunking", "split_plain_text_fixed_tokens"),
    "get_rag_provider": ("core.rag.factory", "get_rag_provider"),
    "apply_rerank_after_retrieve_by_score_desc": (
        "core.rag.post_retrieval_rerank",
        "apply_rerank_after_retrieve_by_score_desc",
    ),
    "apply_rerank_after_retrieve_grouped_by_score_desc": (
        "core.rag.post_retrieval_rerank",
        "apply_rerank_after_retrieve_grouped_by_score_desc",
    ),
    "AgentsetRAGProvider": ("core.rag.providers", "AgentsetRAGProvider"),
    "PgVectorProvider": ("core.rag.providers", "PgVectorProvider"),
}

__all__ = [
    "BaseRAGProvider",
    "RAGChunk",
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "IndexProfileConfig",
    "IndexProfileLexicalConfig",
    "IndexProfileSearchDefaults",
    "IndexProfileSplitConfig",
    "IndexProfileSplitStrategy",
    "RerankerSearchDefaults",
    "SearchChannelsDefaults",
    "RAG_IN_PROCESS_PROVIDER_ID",
    "RAG_API_V1_PREFIX",
    "SEARCH_REQUEST_OPTION_KEYS",
    "build_namespace_search_json_body",
    "build_namespace_search_path",
    "filter_search_request_options",
    "merge_search_request_options",
    "resolve_split_config",
    "split_file_extract",
    "split_plain_text_fixed_tokens",
    "get_rag_provider",
    "apply_rerank_after_retrieve_by_score_desc",
    "apply_rerank_after_retrieve_grouped_by_score_desc",
    "AgentsetRAGProvider",
    "PgVectorProvider",
]


def __getattr__(name: str) -> _LazyExportValue:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = type_cast("_LazyExportValue", getattr(import_module(module_name), attr_name))
    globals()[name] = value
    return value
