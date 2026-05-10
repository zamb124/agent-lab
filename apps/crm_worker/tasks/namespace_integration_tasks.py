"""
TaskIQ: фоновая синхронизация интеграций namespace (сущности и справочники полей).

Диспетчеризация по task.data: provider_id, job (entities | custom_fields).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from apps.crm.container import get_crm_container
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from apps.crm_worker.tasks.knowledge_import_tasks import _notify_task_user
from core.logging import get_logger
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)


class NamespaceIntegrationCancelled(Exception):
    """Прерывание синка: пользователь запросил отмену (cancel_requested в БД)."""


def _stats_message(stats: dict[str, int]) -> str:
    parts = [f"{k}={v}" for k, v in sorted(stats.items())]
    return ", ".join(parts) if parts else ""


def _notification_title(label: str, *, job: str, ok: bool) -> str:
    if job == "custom_fields":
        if ok:
            return f"{label}: справочник полей обновлён"
        return f"{label}: ошибка синхронизации полей"
    if ok:
        return f"{label}: импорт сущностей завершён"
    return f"{label}: ошибка импорта сущностей"


def _notification_cancelled_title(label: str, *, job: str) -> str:
    if job == "custom_fields":
        return f"{label}: синхронизация полей отменена"
    return f"{label}: импорт сущностей отменён"


# Без broker retry: длинный пайплайн и WS; повтор без явной идемпотентности по этапам даёт дубли UI.
@broker.task
async def run_namespace_integration_job(
    task_id: str,
    company_id: str,
    auth_token: Optional[str],
    interface_language: str,
) -> dict[str, Any]:
    container = get_crm_container()
    repo = container.task_repository
    row = await repo.get_for_worker(task_id, company_id)
    if row is None:
        raise ValueError(f"Задача не найдена: {task_id}")
    if row.task_type != "namespace_integration_job":
        raise ValueError(
            f"Ожидался тип namespace_integration_job, получен {row.task_type}"
        )

    data = row.data
    provider_raw = data.get("provider_id")
    job_raw = data.get("job")
    if not isinstance(provider_raw, str) or not provider_raw.strip():
        raise ValueError("В data задачи нет provider_id")
    if job_raw not in ("entities", "custom_fields"):
        raise ValueError(f"В data задачи неизвестный job: {job_raw}")
    provider_id = provider_raw.strip()
    job = str(job_raw)

    if row.status == "cancelled":
        return {"status": "cancelled", "task_id": task_id}

    await _set_crm_context(
        company_id,
        row.namespace,
        auth_token,
        row.user_id,
        interface_language=interface_language,
    )
    connector = container.integration_registry.get(provider_id)
    label = connector.worker_short_label()

    async def _complete_cancel_if_requested() -> bool:
        task_row = await repo.get_for_worker(task_id, company_id)
        if task_row is None:
            return False
        if task_row.status == "cancelled":
            raise NamespaceIntegrationCancelled()
        if not task_row.cancel_requested:
            return False
        pct = int(task_row.progress_pct)
        now = datetime.now(timezone.utc)
        await repo.patch_progress(
            task_id,
            company_id,
            status="cancelled",
            stage="cancelled",
            progress_pct=pct,
            completed_at=now,
            cancel_requested=False,
        )
        title = _notification_cancelled_title(label, job=job)
        await _notify_task_user(
            row.user_id,
            task_id=task_id,
            task_type="namespace_integration_job",
            namespace=row.namespace,
            status="cancelled",
            stage="cancelled",
            progress_pct=pct,
            title=title,
            message="",
        )
        return True

    if await _complete_cancel_if_requested():
        return {"status": "cancelled", "task_id": task_id}

    trace_name = f"crm.worker.namespace_integration.{provider_id}.{job}"
    try:
        async with traced_operation(
            trace_name,
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_task",
            resource_id=task_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: row.user_id,
            },
        ):

            async def on_progress(stage: str, pct: int) -> None:
                if await _complete_cancel_if_requested():
                    raise NamespaceIntegrationCancelled()
                await repo.patch_progress(
                    task_id,
                    company_id,
                    stage=stage,
                    progress_pct=pct,
                )

            if job == "entities":
                stats = await connector.sync_entities(row.namespace, on_progress=on_progress)
            else:
                stats = await connector.sync_custom_field_catalog(
                    row.namespace,
                    on_progress=on_progress,
                )

        terminal = await repo.get_for_worker(task_id, company_id)
        if terminal is not None and terminal.status == "cancelled":
            return {"status": "cancelled", "task_id": task_id}

        await repo.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
            data_patch={"stats": stats},
        )
        title = _notification_title(label, job=job, ok=True)
        msg = _stats_message(stats)
        await _notify_task_user(
            row.user_id,
            task_id=task_id,
            task_type="namespace_integration_job",
            namespace=row.namespace,
            status="completed",
            stage="completed",
            progress_pct=100,
            title=title,
            message=msg,
        )
        return {"status": "completed", "task_id": task_id, "stats": stats}
    except NamespaceIntegrationCancelled:
        return {"status": "cancelled", "task_id": task_id}
    except Exception as exc:
        err_text = str(exc)
        after_exc = await repo.get_for_worker(task_id, company_id)
        if after_exc is not None and after_exc.status == "cancelled":
            return {"status": "cancelled", "task_id": task_id}
        logger.exception(
            "namespace_integration_job failed task_id=%s provider=%s job=%s",
            task_id,
            provider_id,
            job,
        )
        await repo.patch_progress(
            task_id,
            company_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
            error_message=err_text,
        )
        title = _notification_title(label, job=job, ok=False)
        await _notify_task_user(
            row.user_id,
            task_id=task_id,
            task_type="namespace_integration_job",
            namespace=row.namespace,
            status="failed",
            stage="failed",
            progress_pct=100,
            title=title,
            message=err_text[:500],
        )
        raise
