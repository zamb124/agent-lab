"""
Клиент для отправки задач в RAG Worker через TaskIQ.

Используется apps/rag для делегирования тяжелых операций
с pgvector (индексация, поиск) специализированному RAG Worker.
"""

from typing import Dict, Any, List, Optional
from core.logging import get_logger
from apps.rag_worker.tasks.indexing_tasks import delete_document_task, index_rag_document_s3_task
from apps.rag_worker.tasks.search_tasks import search_task
from apps.rag_worker.tasks.maintenance_tasks import list_documents_task, cleanup_namespace_task

logger = get_logger(__name__)


class RAGWorkerClient:
    """
    Клиент для отправки задач в RAG Worker.

    RAG Worker обрабатывает все операции с vector_documents:
    - Индексация документов из S3
    - Семантический поиск
    - Удаление документов
    - Обслуживание namespace
    """

    async def upload_document(
        self,
        namespace_id: str,
        s3_key: str,
        document_name: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Отправляет задачу индексации в RAG Worker."""
        company_id = metadata.get("company_id")
        if not company_id or str(company_id).strip() == "":
            raise ValueError("metadata.company_id обязателен для RAGWorkerClient.upload_document")
        task = await index_rag_document_s3_task.kiq(
            company_id=str(company_id).strip(),
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata,
        )

        logger.info(f"RAG: задача индексации {document_name}, task_id={task.task_id}")

        return {
            "task_id": task.task_id,
            "status": "processing",
            "document_name": document_name,
        }

    async def delete_document(
        self,
        namespace_id: str,
        document_id: str,
        company_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Отправляет задачу удаления документа в RAG Worker."""
        task = await delete_document_task.kiq(
            namespace_id=namespace_id,
            document_id=document_id,
            company_id=company_id,
            user_id=user_id,
        )

        logger.info(f"RAG: задача удаления {document_id}, task_id={task.task_id}")

        return {
            "task_id": task.task_id,
            "status": "processing",
            "document_id": document_id,
        }

    async def search(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Синхронный поиск через RAG Worker с ожиданием результата."""
        logger.info(f"RAG: поиск в namespace {namespace_id}, query='{query[:50]}'")

        result = await search_task.kiq(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters,
        ).wait_result(timeout=timeout)

        logger.info(f"RAG: поиск завершен, найдено {len(result)} результатов")

        return result

    async def search_async(
        self,
        namespace_id: str,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Асинхронный поиск через RAG Worker без ожидания результата."""
        task = await search_task.kiq(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters,
        )

        logger.info(f"RAG: задача поиска, task_id={task.task_id}")

        return {
            "task_id": task.task_id,
            "status": "processing",
            "query": query,
        }

    async def list_documents(
        self,
        namespace_id: str,
        timeout: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """Получить список всех документов в namespace."""
        result = await list_documents_task.kiq(
            namespace_id=namespace_id,
        ).wait_result(timeout=timeout)

        return result

    async def cleanup_namespace(
        self,
        namespace_id: str,
    ) -> Dict[str, Any]:
        """Отправляет задачу очистки namespace."""
        task = await cleanup_namespace_task.kiq(
            namespace_id=namespace_id,
        )

        logger.info(f"RAG: задача очистки namespace {namespace_id}, task_id={task.task_id}")

        return {
            "task_id": task.task_id,
            "status": "processing",
            "namespace": namespace_id,
        }
