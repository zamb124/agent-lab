from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMTask
from apps.crm.scheduled_task_constants import CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(
    task_name=CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    queue_name="crm",
    retry_on_error=True,
    max_retries=3,
)
async def crm_generate_namespace_suggests_tick(
    company_id: str,
    namespace: str,
    schedule_task_id: str | None = None,
) -> dict[str, Any]:
    """Генерация саджестов (дубли/пропущенные) для namespace по крону."""
    logger.info(
        "crm.suggests.generate.started",
        service="crm_worker",
        company_id=company_id,
        namespace=namespace,
    )

    container = get_crm_container()
    repo = container.task_repository
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await repo.create(
        CRMTask(
            task_id=task_id,
            task_type="namespace_suggests_tick",
            status="running",
            stage="running",
            progress_pct=10,
            company_id=company_id,
            namespace=namespace,
            user_id="system",
            data={"schedule_task_id": schedule_task_id},
            started_at=now,
        )
    )

    await _set_crm_context(company_id=company_id, namespace=namespace, interface_language=None)

    try:
        summary = await container.suggest_service.generate_namespace_suggests(
            company_id=company_id,
            namespace=namespace,
        )
        done = datetime.now(timezone.utc)
        await repo.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=done,
            data_patch=dict(summary),
        )
        logger.info(
            "crm.suggests.generate.finished",
            service="crm_worker",
            company_id=company_id,
            namespace=namespace,
            **summary,
        )
        return summary
    except Exception as exc:
        failed_at = datetime.now(timezone.utc)
        await repo.patch_progress(
            task_id,
            company_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=str(exc),
            completed_at=failed_at,
        )
        raise
