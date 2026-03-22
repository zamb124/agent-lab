"""
RAG система с поддержкой различных провайдеров.
Единый интерфейс для работы с векторными хранилищами и семантическим поиском.

Провайдеры:
- agentset: Внешний SaaS (Agentset.ai)
- pgvector: PostgreSQL + pgvector
"""

from .base_provider import BaseRAGProvider
from .models import RAGDocument, RAGSearchResult, RAGNamespace, FlowRAGConfig
from .factory import (
    get_rag_provider,
    get_default_rag_provider,
    close_default_rag_provider
)
from .repository import RAGRepository
from .providers import AgentsetRAGProvider, PgVectorProvider
from .services import DocumentParser, EmbeddingService

__all__ = [
    # Base
    "BaseRAGProvider",
    # Models
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "FlowRAGConfig",
    # Factory
    "get_rag_provider",
    "get_default_rag_provider",
    "close_default_rag_provider",
    # Repository
    "RAGRepository",
    # Providers
    "AgentsetRAGProvider",
    "PgVectorProvider",
    # Services
    "DocumentParser",
    "EmbeddingService",
]

