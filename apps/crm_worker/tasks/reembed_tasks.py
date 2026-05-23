"""
Перевекторизация устаревших чанков CRM ``vector_documents``.

Тонкая обёртка: вся логика в ``core.rag.reembed_stale_documents.execute_reembed_tick``
(биллинг и контекст — по ``vector_documents.company_id``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict

from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMTask
from apps.crm.scheduled_task_constants import CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME
from apps.crm.services.task_service import ALL_NAMESPACES_TASK_KEY
from apps.crm_worker.broker import broker
from core.rag.reembed_stale_documents import execute_reembed_tick


@broker.task(
    task_name=CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
    queue_name="crm",
    retry_on_error=True,
    max_retries=2,
)
async def crm_reembed_stale_documents_tick(
    schedule_task_id: str,
    company_id: str | None = None,
) -> Dict[str, object]:
    """
    ``company_id`` приходит из ``SchedulerService.create`` в ``task.payload``
    для всех cron-задач; reembed группирует чанки по ``vector_documents.company_id``.
    """
    _ = company_id
    result = await execute_reembed_tick(
        container=get_crm_container(),
        channel="crm_worker",
        schedule_task_id=schedule_task_id,
    )
    raw_by_company = result.get("by_company_written")
    by_company: dict[str, int] = {}
    if isinstance(raw_by_company, dict):
        for k, v in raw_by_company.items():
            if isinstance(k, str) and isinstance(v, int):
                by_company[k] = v

    container = get_crm_container()
    repo = container.task_repository
    now = datetime.now(timezone.utc)
    skipped_flag = result.get("skipped") is True
    for cid, cnt in sorted(by_company.items()):
        if cnt <= 0:
            continue
        task_row_id = str(uuid.uuid4())
        await repo.create(
            CRMTask(
                task_id=task_row_id,
                task_type="reembed_stale_documents_tick",
                status="completed",
                stage="completed",
                progress_pct=100,
                company_id=cid,
                namespace=ALL_NAMESPACES_TASK_KEY,
                user_id="system",
                data={
                    "schedule_task_id": schedule_task_id,
                    "chunks_reembedded": cnt,
                    "skipped": skipped_flag,
                },
                started_at=now,
                completed_at=now,
            )
        )
    return result
