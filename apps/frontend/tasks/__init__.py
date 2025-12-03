"""
TaskIQ задачи для сервиса frontend.

- send_notification_task: отправка уведомления через WebSocket
- process_rag_document_task: асинхронная обработка документа для RAG
"""

from apps.frontend.tasks.notification_tasks import (
    send_notification_task,
    process_rag_document_task,
)

__all__ = ["send_notification_task", "process_rag_document_task"]

