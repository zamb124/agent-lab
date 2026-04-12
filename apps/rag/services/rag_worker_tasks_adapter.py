"""Реализация ``RagWorkerTasksPort`` через TaskIQ-задачи ``apps.rag_worker.tasks``."""

from __future__ import annotations

from typing import Any

from apps.rag_worker.tasks.indexing_tasks import delete_document_task, index_rag_document_s3_task
from apps.rag_worker.tasks.maintenance_tasks import cleanup_namespace_task, list_documents_task
from core.logging import get_logger
from core.rag.rag_worker_tasks_port import RagWorkerTasksPort

logger = get_logger(__name__)


class RagWorkerTasksAdapter(RagWorkerTasksPort):
    async def enqueue_index_rag_document_s3(
        self,
        *,
        company_id: str,
        namespace_id: str,
        s3_key: str,
        document_name: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        task = await index_rag_document_s3_task.kiq(
            company_id=company_id,
            namespace_id=namespace_id,
            s3_key=s3_key,
            document_name=document_name,
            metadata=metadata,
        )
        task_id = task.task_id
        logger.info("RAG: индексация %s, task_id=%s", document_name, task_id)
        return {
            "task_id": task_id,
            "status": "processing",
            "document_name": document_name,
        }

    async def enqueue_delete_document(
        self,
        *,
        namespace_id: str,
        document_id: str,
    ) -> dict[str, Any]:
        task = await delete_document_task.kiq(
            namespace_id=namespace_id,
            document_id=document_id,
        )
        logger.info("RAG: задача удаления %s, task_id=%s", document_id, task.task_id)
        return {
            "task_id": task.task_id,
            "status": "processing",
            "document_id": document_id,
        }

    async def wait_list_documents(
        self,
        *,
        namespace_id: str,
        timeout: float,
    ) -> list[dict[str, Any]]:
        return await list_documents_task.kiq(
            namespace_id=namespace_id,
        ).wait_result(timeout=timeout)

    async def enqueue_cleanup_namespace(
        self,
        *,
        namespace_id: str,
    ) -> dict[str, Any]:
        task = await cleanup_namespace_task.kiq(namespace_id=namespace_id)
        logger.info("RAG: очистка namespace %s, task_id=%s", namespace_id, task.task_id)
        return {
            "task_id": task.task_id,
            "status": "processing",
            "namespace": namespace_id,
        }
