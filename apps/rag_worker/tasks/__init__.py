"""
Tasks для RAG Worker.
"""

from apps.rag_worker.tasks.indexing_tasks import (
    delete_document_task,
    index_rag_document_s3_task,
)
from apps.rag_worker.tasks.maintenance_tasks import cleanup_namespace_task

__all__ = [
    "index_rag_document_s3_task",
    "delete_document_task",
    "cleanup_namespace_task",
]
