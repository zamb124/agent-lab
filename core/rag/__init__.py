"""
RAG система с поддержкой различных провайдеров.
Единый интерфейс для работы с векторными хранилищами и семантическим поиском.
"""

from .base_provider import BaseRAGProvider
from .models import RAGDocument, RAGSearchResult, RAGNamespace, AgentRAGConfig
from .factory import (
    get_rag_provider,
    get_default_rag_provider,
    close_default_rag_provider
)

__all__ = [
    "BaseRAGProvider",
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "AgentRAGConfig",
    "get_rag_provider",
    "get_default_rag_provider",
    "close_default_rag_provider",
]

