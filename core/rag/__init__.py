"""
RAG система с поддержкой различных провайдеров.
Единый интерфейс для работы с векторными хранилищами и семантическим поиском.

Провайдеры:
- agentset: Внешний SaaS (Agentset.ai)
- pgvector: PostgreSQL + pgvector

Парсинг файлов для индексации: core.files.reader.FileReader (единая схема FileReadResult).
"""

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

from .base_provider import BaseRAGProvider
from .chunking import split_parsed_document, split_plain_text_fixed_tokens
from .constants import RAG_IN_PROCESS_PROVIDER_ID
from .factory import get_rag_provider
from .models import (
    FlowRAGConfig,
    RAGDocument,
    RAGNamespace,
    RAGSearchResult,
)
from .parsed_document import BlockKind, ParsedBlock, ParsedDocument
from .parsing import parse_document_bytes
from .post_retrieval_rerank import (
    RerankerClientError,
    apply_rerank_after_retrieve,
    apply_rerank_after_retrieve_grouped,
)
from .providers import AgentsetRAGProvider, PgVectorProvider
from .rag_http_namespace_search import (
    RAG_API_V1_PREFIX,
    SEARCH_REQUEST_OPTION_KEYS,
    build_namespace_search_json_body,
    build_namespace_search_path,
    filter_search_request_options,
    merge_search_request_options,
)
from .rag_resource import RAGResource
from .rag_resource_bind import RagResourceBindParams
from .repository import RAGRepository
from .services import EmbeddingService

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
    "parse_document_bytes",
    "RAGResource",
    "RAG_IN_PROCESS_PROVIDER_ID",
    "RAG_API_V1_PREFIX",
    "SEARCH_REQUEST_OPTION_KEYS",
    "build_namespace_search_json_body",
    "build_namespace_search_path",
    "filter_search_request_options",
    "merge_search_request_options",
    "RagResourceBindParams",
    "split_parsed_document",
    "split_plain_text_fixed_tokens",
    "get_rag_provider",
    "RAGRepository",
    "RerankerClientError",
    "apply_rerank_after_retrieve",
    "apply_rerank_after_retrieve_grouped",
    "AgentsetRAGProvider",
    "PgVectorProvider",
    "EmbeddingService",
]
