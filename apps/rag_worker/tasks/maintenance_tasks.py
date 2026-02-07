"""
Tasks для обслуживания и очистки vector_documents.
"""

from typing import Dict, Any, List

from apps.rag_worker.broker import broker
from core.rag.factory import get_default_rag_provider
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(queue_name="rag")
async def cleanup_namespace_task(namespace_id: str) -> Dict[str, Any]:
    """
    Очистка namespace -- удаление всех документов.

    Args:
        namespace_id: ID namespace для очистки

    Returns:
        Результат очистки
    """
    logger.info(f"RAG Worker: очистка namespace {namespace_id}")

    provider = get_default_rag_provider()

    success = await provider.delete_namespace(namespace_id)

    logger.info(f"RAG Worker: namespace {namespace_id} очищен")

    return {
        "namespace": namespace_id,
        "status": "cleaned" if success else "empty",
    }


@broker.task(queue_name="rag")
async def list_documents_task(namespace_id: str) -> List[Dict[str, Any]]:
    """
    Получить список всех документов в namespace.

    Args:
        namespace_id: ID namespace

    Returns:
        Список документов с метаданными
    """
    logger.info(f"RAG Worker: получение списка документов в namespace {namespace_id}")

    provider = get_default_rag_provider()
    documents = await provider.list_documents(namespace_id)

    return [
        {
            "document_id": doc.document_id,
            "document_name": doc.name,
            "namespace": doc.namespace,
            "metadata": doc.metadata,
        }
        for doc in documents
    ]


@broker.task(queue_name="rag", retry_on_error=True, max_retries=3)
async def reindex_document_task(
    namespace_id: str,
    document_id: str,
    s3_key: str,
    document_name: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Переиндексация документа (удаление + загрузка заново).

    Args:
        namespace_id: ID namespace
        document_id: ID документа для удаления
        s3_key: Ключ файла в S3
        document_name: Имя документа
        metadata: Метаданные

    Returns:
        Результат переиндексации
    """
    logger.info(f"RAG Worker: переиндексация документа {document_id} в namespace {namespace_id}")

    provider = get_default_rag_provider()

    await provider.delete_document(namespace_id, document_id)

    document = await provider.upload_document_from_s3(
        namespace_id=namespace_id,
        s3_key=s3_key,
        document_name=document_name,
        metadata=metadata,
    )

    logger.info(
        f"RAG Worker: документ {document_name} переиндексирован, document_id={document.document_id}"
    )

    return {
        "old_document_id": document_id,
        "new_document_id": document.document_id,
        "document_name": document.name,
        "namespace": namespace_id,
        "status": "reindexed",
    }
