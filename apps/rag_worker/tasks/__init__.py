"""
Tasks для RAG Worker.
"""

from apps.rag_worker.tasks.indexing_tasks import (
    upload_document_task,
    delete_document_task,
)
from apps.rag_worker.tasks.search_tasks import search_task
from apps.rag_worker.tasks.maintenance_tasks import cleanup_namespace_task

__all__ = [
    "upload_document_task",
    "delete_document_task",
    "search_task",
    "cleanup_namespace_task",
]
