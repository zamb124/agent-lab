"""
RAG система с поддержкой различных провайдеров.
Единый интерфейс для работы с векторными хранилищами и семантическим поиском.

Провайдеры:
- agentset: Внешний SaaS (Agentset.ai)
- chromadb: Локальный ChromaDB Server
"""

from .base_provider import BaseRAGProvider
from .models import RAGDocument, RAGSearchResult, RAGNamespace, AgentRAGConfig
from .factory import (
    get_rag_provider,
    get_default_rag_provider,
    close_default_rag_provider
)
from .repository import RAGRepository
from .providers import AgentsetRAGProvider, ChromaDBRAGProvider
from .services import DocumentParser, EmbeddingService

__all__ = [
    # Base
    "BaseRAGProvider",
    # Models
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "AgentRAGConfig",
    # Factory
    "get_rag_provider",
    "get_default_rag_provider",
    "close_default_rag_provider",
    # Repository
    "RAGRepository",
    # Providers
    "AgentsetRAGProvider",
    "ChromaDBRAGProvider",
    # Services
    "DocumentParser",
    "EmbeddingService",
]

