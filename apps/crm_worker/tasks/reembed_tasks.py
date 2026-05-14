"""
Перевекторизация устаревших чанков CRM ``vector_documents``.

Тонкая обёртка: вся логика в ``core.rag.reembed_stale_documents.execute_reembed_tick``
(биллинг и контекст — по ``vector_documents.company_id``).
"""

from __future__ import annotations

from typing import Dict

from apps.crm.container import get_crm_container
from apps.crm_worker.broker import broker
from core.rag.reembed_stale_documents import execute_reembed_tick


@broker.task(
    task_name="crm_reembed_stale_documents_tick",
    queue_name="crm",
    retry_on_error=True,
    max_retries=2,
)
async def crm_reembed_stale_documents_tick(
    scheduler_task_id: str,
    company_id: str | None = None,
) -> Dict[str, object]:
    """
    ``company_id`` приходит из ``SchedulerService.create`` в ``task.payload``
    для всех cron-задач; reembed группирует чанки по ``vector_documents.company_id``.
    """
    _ = company_id
    return await execute_reembed_tick(
        container=get_crm_container(),
        channel="crm_worker",
        scheduler_task_id=scheduler_task_id,
    )
