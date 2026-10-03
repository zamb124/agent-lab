"""Таблицы platform_rag."""

from core.db.models.rag.processing_status import DocumentProcessingStatus
from core.db.models.rag.vector_document import VectorDocument

__all__ = ["DocumentProcessingStatus", "VectorDocument"]
