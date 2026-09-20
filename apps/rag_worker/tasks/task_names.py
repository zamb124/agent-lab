"""Declaration-модуль RAG задач (очередь ``rag``).

Лёгкий: только объявления. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``).
"""

from core.tasks import declare_task

RAG_INDEX_DOCUMENT_S3 = declare_task(
    "rag_index_document_s3", queue="rag", retry=True, max_retries=3
)
RAG_REINDEX_DOCUMENT = declare_task(
    "rag_reindex_document", queue="rag", retry=True, max_retries=3
)
RAG_DELETE_DOCUMENT = declare_task(
    "rag_delete_document", queue="rag", retry=True, max_retries=3
)
RAG_CLEANUP_NAMESPACE = declare_task("rag_cleanup_namespace", queue="rag")
RAG_LIST_DOCUMENTS = declare_task("rag_list_documents", queue="rag")
RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK = declare_task(
    "rag_cleanup_expired_documents_tick", queue="rag", scheduled=True, retry=True, max_retries=2
)
RAG_REEMBED_STALE_DOCUMENTS_TICK = declare_task(
    "rag_reembed_stale_documents_tick", queue="rag", scheduled=True, retry=True, max_retries=2
)
RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK = declare_task(
    "rag_cleanup_orphan_company_chunks_tick", queue="rag", scheduled=True, retry=True, max_retries=2
)

__all__ = [
    "RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK",
    "RAG_CLEANUP_NAMESPACE",
    "RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK",
    "RAG_DELETE_DOCUMENT",
    "RAG_INDEX_DOCUMENT_S3",
    "RAG_LIST_DOCUMENTS",
    "RAG_REEMBED_STALE_DOCUMENTS_TICK",
    "RAG_REINDEX_DOCUMENT",
]
