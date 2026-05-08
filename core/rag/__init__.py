"""
RAG система с поддержкой различных провайдеров.
Единый интерфейс для работы с векторными хранилищами и семантическим поиском.

Провайдеры:
- agentset: Внешний SaaS (Agentset.ai)
- pgvector: PostgreSQL + pgvector

Парсинг файлов для индексации: core.files.reader.FileReader (единая схема FileReadResult).
"""

from .base_provider import BaseRAGProvider
from .chunking import split_parsed_document, split_plain_text_fixed_tokens
from .factory import get_default_rag_provider, get_rag_provider
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
from .models import (
    FlowRAGConfig,
    RAGDocument,
    RAGNamespace,
    RAGSearchResult,
)
from .parsed_document import BlockKind, ParsedBlock, ParsedDocument
from .parsing import parse_document_bytes
from .rag_resource import RAGResource
from .rag_resource_bind import RagResourceBindParams
from .rag_worker_tasks_port import RagWorkerTasksPort
from .providers import AgentsetRAGProvider, PgVectorProvider
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
    "RagResourceBindParams",
    "RagWorkerTasksPort",
    "split_parsed_document",
    "split_plain_text_fixed_tokens",
    "get_default_rag_provider",
    "get_rag_provider",
    "RAGRepository",
    "AgentsetRAGProvider",
    "PgVectorProvider",
    "EmbeddingService",
]
