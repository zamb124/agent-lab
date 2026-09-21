"""
Cron: unified синхронизация интеграции namespace (entities, затем custom_fields).

Параметры приходят из platform scheduler payload (см. SchedulerService.create).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.crm.container import get_crm_container
from apps.crm.db.models import CRMTask
from apps.crm_worker.tasks.crm_context import (
    build_auth_token_for_company,
    set_crm_context,
)
from apps.crm_worker.tasks.task_names import SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC
from core.logging import get_logger
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)


@platform_task(SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC)
async def scheduled_namespace_integration_unified_sync(
    schedule_task_id: str,
    company_id: str,
    namespace: str,
    provider_id: str,
    oauth_user_id: str,
) -> JsonObject:
    ns = namespace.strip()
    pid = provider_id.strip()
    uid = oauth_user_id.strip()
    if not ns:
        raise ValueError("namespace is required")
    if not pid:
        raise ValueError("provider_id is required")
    if not uid:
        raise ValueError("oauth_user_id is required")

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
            logger.info("crm.scheduled_namespace_integration_unified_sync", job=job, task_id=existing.task_id)
            skip_now = datetime.now(timezone.utc)
            skip_tid = str(uuid.uuid4())
            _ = await repo.create(
                CRMTask(
                    task_id=skip_tid,
                    task_type="scheduled_namespace_integration_sync",
                    status="completed",
                    stage="skipped_active_integration_job",
                    progress_pct=100,
                    company_id=company_id,
                    namespace=ns,
                    user_id=uid,
                    data={
                        "schedule_task_id": schedule_task_id,
                        "provider_id": pid,
                        "blocking_task_id": existing.task_id,
                        "blocking_job": job,
                        "reason": "active_namespace_integration_job",
                    },
                    started_at=skip_now,
                    completed_at=skip_now,
                )
            )
            return {
                "status": "skipped",
                "reason": "active_namespace_integration_job",
                "blocking_task_id": existing.task_id,
                "blocking_job": job,
                "schedule_task_id": schedule_task_id,
            }

    sync_task_id = str(uuid.uuid4())
    sync_started = datetime.now(timezone.utc)
    _ = await repo.create(
        CRMTask(
            task_id=sync_task_id,
            task_type="scheduled_namespace_integration_sync",
            status="running",
            stage="sync_entities",
            progress_pct=10,
            company_id=company_id,
            namespace=ns,
            user_id=uid,
            data={"schedule_task_id": schedule_task_id, "provider_id": pid},
            started_at=sync_started,
        )
    )

    auth_token = await build_auth_token_for_company(company_id, uid)
    await set_crm_context(
        company_id,
        ns,
        auth_token=auth_token,
        user_id=uid,
        interface_language="ru",
    )

    try:
        connector = container.integration_registry.get(pid)
        entities_stats = await connector.sync_entities(ns)
        await repo.patch_progress(
            sync_task_id,
            company_id,
            status="running",
            stage="sync_custom_fields",
            progress_pct=50,
        )
        fields_stats = await connector.sync_custom_field_catalog(ns)

        done_patch: JsonObject = {
            "schedule_task_id": schedule_task_id,
            "provider_id": pid,
        }
        done_patch["entities_stats"] = {key: value for key, value in entities_stats.items()}
        done_patch["fields_stats"] = {key: value for key, value in fields_stats.items()}

        done_at = datetime.now(timezone.utc)
        await repo.patch_progress(
            sync_task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=done_at,
            data_patch=done_patch,
        )

        logger.info(
            "crm.scheduled_namespace_integration_unified_sync.done",
            company_id=company_id,
            namespace=ns,
            provider=pid,
            schedule_task_id=schedule_task_id,
            entities_stats=entities_stats,
            fields_stats=fields_stats,
        )
        return {
            "status": "completed",
            "schedule_task_id": schedule_task_id,
            "entities_stats": done_patch["entities_stats"],
            "fields_stats": done_patch["fields_stats"],
        }
    except Exception as exc:
        fail_at = datetime.now(timezone.utc)
        await repo.patch_progress(
            sync_task_id,
            company_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=str(exc),
            completed_at=fail_at,
        )
        raise
