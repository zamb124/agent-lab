"""Base для env Alembic и таблицы RAG."""

from core.db.models.base import Base
from core.db.models.rag import (
    DocumentProcessingStatus,
    VectorDocument,
)

__all__ = [
    "Base",
    "DocumentProcessingStatus",
    "VectorDocument",
]
