"""
Порт постановки задач RAG Worker (TaskIQ): реализация только в ``apps`` (импорт задач воркера).

``RAGRepository`` вызывает методы порта для асинхронной индексации/удаления без зависимости ``core`` от ``apps.rag_worker``.
"""

from __future__ import annotations

from typing import Any, Protocol


class RagWorkerTasksPort(Protocol):
    """Постановка и ожидание задач очереди ``rag`` (индексация S3, удаление, список, очистка namespace)."""

    async def enqueue_index_rag_document_s3(
        self,
        *,
        company_id: str,
        namespace_id: str,
        s3_key: str,
        document_name: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Возвращает словарь с ``task_id``, ``status``, ``document_name``."""

    async def enqueue_delete_document(
        self,
        *,
        namespace_id: str,
        document_id: str,
    ) -> dict[str, Any]:
        """Возвращает словарь с ``task_id``, ``status``, ``document_id``."""

    async def wait_list_documents(
        self,
        *,
        namespace_id: str,
        timeout: float,
    ) -> list[dict[str, Any]]:
        """Ожидает результат задачи списка документов."""

    async def enqueue_cleanup_namespace(
        self,
        *,
        namespace_id: str,
    ) -> dict[str, Any]:
        """Возвращает словарь с ``task_id``, ``status``, ``namespace``."""
