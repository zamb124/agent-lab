"""
Cron: unified синхронизация интеграции namespace (entities, затем custom_fields).

Параметры приходят из platform scheduler payload (см. SchedulerService.create).
"""

from __future__ import annotations

from typing import Any

from apps.crm.container import get_crm_container
from apps.crm.scheduled_integration_constants import (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
)
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import (
    _build_auth_token_for_company,
    _set_crm_context,
)
from core.logging import get_logger

logger = get_logger(__name__)


@broker.task(
    task_name=SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
    queue_name="crm",
    retry_on_error=True,
    max_retries=2,
)
async def scheduled_namespace_integration_unified_sync(
    scheduler_task_id: str,
    company_id: str,
    namespace: str,
    provider_id: str,
    oauth_user_id: str,
) -> dict[str, Any]:
    ns = namespace.strip()
    pid = provider_id.strip()
    uid = oauth_user_id.strip()
    if not ns:
        raise ValueError("namespace обязателен")
    if not pid:
        raise ValueError("provider_id обязателен")
    if not uid:
        raise ValueError("oauth_user_id обязателен")

    container = get_crm_container()
    repo = container.task_repository

    for job in ("entities", "custom_fields"):
        existing = await repo.find_active_by_data_keys(
            "namespace_integration_job",
            {"provider_id": pid, "job": job},
            ns,
            company_id,
        )
        if existing is not None:
            logger.info(
                "scheduled_namespace_integration_unified_sync: skip tick, active job %s task_id=%s",
                job,
                existing.task_id,
            )
            return {
                "status": "skipped",
                "reason": "active_namespace_integration_job",
                "blocking_task_id": existing.task_id,
                "blocking_job": job,
                "scheduler_task_id": scheduler_task_id,
            }

    auth_token = await _build_auth_token_for_company(company_id, uid)
    _set_crm_context(
        company_id,
        ns,
        auth_token=auth_token,
        user_id=uid,
        interface_language="ru",
    )

    connector = container.integration_registry.get(pid)
    entities_stats = await connector.sync_entities(ns)
    fields_stats = await connector.sync_custom_field_catalog(ns)

    logger.info(
        "scheduled_namespace_integration_unified_sync: done company=%s ns=%s provider=%s "
        "scheduler_task_id=%s entities=%s fields=%s",
        company_id,
        ns,
        pid,
        scheduler_task_id,
        entities_stats,
        fields_stats,
    )
    return {
        "status": "completed",
        "scheduler_task_id": scheduler_task_id,
        "entities_stats": entities_stats,
        "fields_stats": fields_stats,
    }
