"""
TaskIQ: анализ заметки (analyze / apply / process).

Задача всегда создаётся через TaskService.start_note_analyze, получает task_id.
Обновляет этапы в crm_tasks и шлёт WebSocket-уведомления на каждом переходе.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

import core.tracing.attributes as trace_attributes
from apps.crm.container import get_crm_container
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import NoteProcessingConfig
from apps.crm.services.crm_task_ws_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.services.entity_service import ApplyAnalysisDraftEntityFailuresError
from apps.crm.taskiq_analyze_errors import format_validation_for_taskiq
from apps.crm_worker.broker import broker
from apps.crm_worker.task_names import CRM_PROCESS_NOTE_TASK_NAME
from apps.crm_worker.tasks.daily_summary_tasks import set_crm_context
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


async def _notify_analyze_stage(
    user_id: str,
    repo: TaskRepository,
    company_id: str,
    *,
    task_id: str,
    namespace: str,
    status: str,
    stage: str,
    progress_pct: int,
    message: str,
) -> None:
    await notify_user(
        user_id,
        Notification(
            type=NotificationType.CRM_TASK_UPDATED,
            title="Анализ заметки",
            message=message,
            service="crm",
            data={
                "task_id": task_id,
                "task_type": "note_analyze",
                "namespace": namespace,
                "status": status,
                "stage": stage,
                "progress_pct": progress_pct,
            },
        ),
    )
    await publish_crm_task_snapshot_for_user(
        user_id=user_id,
        repo=repo,
        task_id=task_id,
        company_id=company_id,
    )


# Без broker retry: этапы анализа и WS; повтор без отдельной идемпотентности по task_id даёт дубли UI.
@broker.task(task_name=CRM_PROCESS_NOTE_TASK_NAME, queue_name="crm")
async def process_note_task(
    task_id: str,
    note_id: str,
    company_id: str,
    namespace: str,
    auth_token: str | None,
    user_id: str,
    interface_language: str,
    config_payload: JsonObject,
    mode: str,
) -> JsonObject:
    """mode: 'analyze' | 'apply' | 'process'."""
    await set_crm_context(company_id, namespace, auth_token, user_id, interface_language=interface_language)
    container = get_crm_container()
    repo = container.task_repository
    pipeline = container.note_processing_service

    try:
        config = NoteProcessingConfig.model_validate(config_payload)
    except ValidationError as exc:
        raise ValueError(format_validation_for_taskiq(exc.errors())) from exc

    async def _progress(stage: str, pct: int, msg: str = "") -> None:
        await repo.patch_progress(
            task_id, company_id,
            status="running", stage=stage, progress_pct=pct,
        )
        await _notify_analyze_stage(
            user_id,
            repo,
            company_id,
            task_id=task_id,
            namespace=namespace,
            status="running",
            stage=stage,
            progress_pct=pct,
            message=msg or stage,
        )

    async def _check_cancel() -> bool:
        task_row = await repo.get_for_worker(task_id, company_id)
        if task_row is not None and task_row.cancel_requested:
            await repo.patch_progress(
                task_id, company_id,
                status="cancelled", stage="cancelled", progress_pct=100,
                completed_at=datetime.now(timezone.utc),
            )
            await _notify_analyze_stage(
                user_id,
                repo,
                company_id,
                task_id=task_id,
                namespace=namespace,
                status="cancelled",
                stage="cancelled",
                progress_pct=100,
                message="Задача отменена",
            )
            return True
        return False

    if await _check_cancel():
        return {"status": "cancelled", "task_id": task_id}

    try:
        await container.entity_service.clear_note_analysis_error(note_id)
        async with traced_operation(
            f"crm.worker.note_{mode}",
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_task",
            resource_id=task_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: user_id,
            },
        ):
            if mode == "analyze":
                await _progress("reading_attachments", 15, "Чтение вложений")
                if await _check_cancel():
                    return {"status": "cancelled", "task_id": task_id}
                result = await pipeline.analyze(note_id, config, progress_cb=_progress)
                result_data = require_json_object(
                    result.model_dump(mode="json"), "note_processing.analyze_result"
                )
                entities_count = len(result.entities)
                rel_count = len(result.relationships)
            elif mode == "apply":
                await _progress("applying", 88, "Применение черновика")
                if await _check_cancel():
                    return {"status": "cancelled", "task_id": task_id}
                result = await pipeline.apply(note_id, progress_cb=_progress)
                result_data = require_json_object(
                    result.model_dump(mode="json"), "note_processing.apply_result"
                )
                entities_count = len(result.created_entity_ids) + len(result.updated_entity_ids)
                rel_count = len(result.created_relationship_ids)
            elif mode == "process":
                await _progress("reading_attachments", 15, "Чтение вложений")
                if await _check_cancel():
                    return {"status": "cancelled", "task_id": task_id}
                result = await pipeline.process(note_id, config, progress_cb=_progress)
                result_data = require_json_object(
                    result.model_dump(mode="json"), "note_processing.process_result"
                )
                entities_count = len(result.created_entity_ids) + len(result.updated_entity_ids)
                rel_count = len(result.created_relationship_ids)
            else:
                raise ValueError(f"Unknown mode: {mode}")
    except ApplyAnalysisDraftEntityFailuresError as exc:
        failures_payload: list[dict[str, str]] = [
            {
                "draft_entity_id": did,
                "entity_name": name if name is not None else "",
                "entity_type": etype if etype is not None else "",
                "message": msg,
            }
            for did, name, etype, msg in exc.failures
        ]
        err_msg = str(exc)
        await repo.patch_progress(
            task_id,
            company_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            error_message=err_msg,
            completed_at=datetime.now(timezone.utc),
        )
        await container.entity_service.record_note_analysis_failure(
            note_id,
            err_msg,
            apply_failures=failures_payload,
        )
        await _notify_analyze_stage(
            user_id,
            repo,
            company_id,
            task_id=task_id,
            namespace=namespace,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=err_msg[:200],
        )
        raise ValueError(err_msg) from exc
    except ValidationError as exc:
        err_msg = format_validation_for_taskiq(exc.errors())
        await repo.patch_progress(
            task_id, company_id,
            status="failed", stage="failed", progress_pct=100,
            error_message=err_msg,
            completed_at=datetime.now(timezone.utc),
        )
        await container.entity_service.record_note_analysis_failure(note_id, err_msg)
        await _notify_analyze_stage(
            user_id,
            repo,
            company_id,
            task_id=task_id,
            namespace=namespace,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=err_msg[:200],
        )
        raise ValueError(err_msg) from exc
    except Exception as exc:
        err_msg = str(exc)
        logger.exception("note_analyze failed task_id=%s note_id=%s", task_id, note_id)
        await repo.patch_progress(
            task_id, company_id,
            status="failed", stage="failed", progress_pct=100,
            error_message=err_msg,
            completed_at=datetime.now(timezone.utc),
        )
        await container.entity_service.record_note_analysis_failure(note_id, err_msg)
        await _notify_analyze_stage(
            user_id,
            repo,
            company_id,
            task_id=task_id,
            namespace=namespace,
            status="failed",
            stage="failed",
            progress_pct=100,
            message=err_msg[:200],
        )
        raise

    await repo.patch_progress(
        task_id, company_id,
        status="completed", stage="completed", progress_pct=100,
        completed_at=datetime.now(timezone.utc),
        data_patch={
            "result_entities_count": entities_count,
            "result_relationships_count": rel_count,
        },
    )
    await _notify_analyze_stage(
        user_id,
        repo,
        company_id,
        task_id=task_id,
        namespace=namespace,
        status="completed",
        stage="completed",
        progress_pct=100,
        message=f"Найдено сущностей: {entities_count}, связей: {rel_count}",
    )
    return result_data
