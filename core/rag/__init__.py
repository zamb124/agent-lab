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
    IndexProfileParsingConfig,
    IndexProfileSearchDefaults,
    IndexProfileSplitConfig,
    IndexProfileSplitStrategy,
    RerankerSearchDefaults,
    SearchChannelsDefaults,
)

from .constants import RAG_IN_PROCESS_PROVIDER_ID
from .models import FlowRAGConfig, RAGDocument, RAGNamespace, RAGSearchResult
from .rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    SEARCH_REQUEST_OPTION_KEYS,
    build_namespace_search_json_body,
    build_namespace_search_path,
    filter_search_request_options,
    merge_search_request_options,
)
from .rag_resource_bind import RagResourceBindParams, RagResourceBindPatch

if TYPE_CHECKING:
    from types import FunctionType, UnionType

    from .base_provider import BaseRAGProvider
    from .chunking import split_parsed_document, split_plain_text_fixed_tokens
    from .factory import get_rag_provider
    from .llm_context_memory_store import (
        RAGLLMContextMemoryStore,
        llm_context_memory_namespace_id,
    )
    from .llm_context_source import RAGLLMContextSource
    from .parsed_document import BlockKind, ParsedBlock, ParsedDocument
    from .post_retrieval_rerank import (
        RerankerClientError,
        apply_rerank_after_retrieve,
        apply_rerank_after_retrieve_grouped,
    )
    from .providers import AgentsetRAGProvider, PgVectorProvider
    from .rag_resource import RAGResource
    from .repository import RAGRepository
    from .services import EmbeddingService

    type _LazyExportValue = (
        type[BaseRAGProvider]
        | type[BlockKind]
        | type[ParsedBlock]
        | type[ParsedDocument]
        | type[RAGResource]
        | type[RAGRepository]
        | type[RAGLLMContextSource]
        | type[RAGLLMContextMemoryStore]
        | type[RerankerClientError]
        | type[AgentsetRAGProvider]
        | type[PgVectorProvider]
        | type[EmbeddingService]
        | FunctionType
        | UnionType
    )

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseRAGProvider": ("core.rag.base_provider", "BaseRAGProvider"),
    "BlockKind": ("core.rag.parsed_document", "BlockKind"),
    "ParsedBlock": ("core.rag.parsed_document", "ParsedBlock"),
    "ParsedDocument": ("core.rag.parsed_document", "ParsedDocument"),
    "RAGResource": ("core.rag.rag_resource", "RAGResource"),
    "split_parsed_document": ("core.rag.chunking", "split_parsed_document"),
    "split_plain_text_fixed_tokens": ("core.rag.chunking", "split_plain_text_fixed_tokens"),
    "get_rag_provider": ("core.rag.factory", "get_rag_provider"),
    "RAGRepository": ("core.rag.repository", "RAGRepository"),
    "RAGLLMContextSource": ("core.rag.llm_context_source", "RAGLLMContextSource"),
    "RAGLLMContextMemoryStore": (
        "core.rag.llm_context_memory_store",
        "RAGLLMContextMemoryStore",
    ),
    "llm_context_memory_namespace_id": (
        "core.rag.llm_context_memory_store",
        "llm_context_memory_namespace_id",
    ),
    "RerankerClientError": ("core.rag.post_retrieval_rerank", "RerankerClientError"),
    "apply_rerank_after_retrieve": (
        "core.rag.post_retrieval_rerank",
        "apply_rerank_after_retrieve",
    ),
    "apply_rerank_after_retrieve_grouped": (
        "core.rag.post_retrieval_rerank",
        "apply_rerank_after_retrieve_grouped",
    ),
    "AgentsetRAGProvider": ("core.rag.providers", "AgentsetRAGProvider"),
    "PgVectorProvider": ("core.rag.providers", "PgVectorProvider"),
    "EmbeddingService": ("core.rag.services", "EmbeddingService"),
}

__all__ = [
    "BaseRAGProvider",
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "FlowRAGConfig",
    "IndexProfileConfig",
    "IndexProfileLexicalConfig",
    "IndexProfileParsingConfig",
    "IndexProfileSearchDefaults",
    "IndexProfileSplitConfig",
    "IndexProfileSplitStrategy",
    "RerankerSearchDefaults",
    "SearchChannelsDefaults",
    "BlockKind",
    "ParsedBlock",
    "ParsedDocument",
    "RAGResource",
    "RAG_IN_PROCESS_PROVIDER_ID",
    "RAG_API_V1_PREFIX",
    "SEARCH_REQUEST_OPTION_KEYS",
    "build_namespace_search_json_body",
    "build_namespace_search_path",
    "filter_search_request_options",
    "merge_search_request_options",
    "RagResourceBindParams",
    "RagResourceBindPatch",
    "split_parsed_document",
    "split_plain_text_fixed_tokens",
    "get_rag_provider",
    "RAGRepository",
    "RAGLLMContextSource",
    "RAGLLMContextMemoryStore",
    "llm_context_memory_namespace_id",
    "RerankerClientError",
    "apply_rerank_after_retrieve",
    "apply_rerank_after_retrieve_grouped",
    "AgentsetRAGProvider",
    "PgVectorProvider",
    "EmbeddingService",
]


def __getattr__(name: str) -> _LazyExportValue:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = type_cast("_LazyExportValue", getattr(import_module(module_name), attr_name))
    globals()[name] = value
    return value
