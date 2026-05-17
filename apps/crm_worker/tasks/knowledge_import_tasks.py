"""
TaskIQ: импорт базы знаний.

Пайплайн: (1) нарезка текста → создание сущностей note (как при ручной заметке);
(2) при mode=graph — для каждой note вызывается NoteProcessingService.process()
(analyze + apply через единый конвейер). Режим notes_only — только фаза 1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import core.tracing.attributes as trace_attributes
from apps.crm.container import get_crm_container
from apps.crm.models.api import NoteProcessingConfig
from apps.crm.services.crm_task_ws_broadcast import publish_crm_task_snapshot_for_user
from apps.crm.services.file_text_reader import load_text_from_stored_file_id
from apps.crm.services.knowledge_import_text_redis import (
    delete_pending_import_text,
    get_pending_import_text,
)
from apps.crm_worker.broker import broker
from apps.crm_worker.task_names import CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.utils.knowledge_text_split import split_knowledge_text
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


def _optional_payload_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    raise ValueError(f"data.{key} должен быть строкой")


def _payload_str_list(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"data.{key} должен быть списком строк")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"data.{key} должен быть списком строк")
        stripped = item.strip()
        if stripped:
            result.append(stripped)
    return result


def _optional_payload_str_list(data: dict[str, object], key: str) -> list[str] | None:
    if data.get(key) is None:
        return None
    return _payload_str_list(data, key)


def _payload_int(data: dict[str, object], key: str, *, default: int) -> int:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"data.{key} должен быть целым числом")
    return value


def _payload_bool(data: dict[str, object], key: str, *, default: bool) -> bool:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"data.{key} должен быть boolean")
    return value


async def _notify_task_user(
    user_id: str,
    repo,
    company_id: str,
    *,
    task_id: str,
    task_type: str,
    namespace: str,
    status: str,
    stage: str,
    progress_pct: int,
    title: str,
    message: str,
) -> None:
    await notify_user(
        user_id,
        Notification(
            type=NotificationType.CRM_TASK_UPDATED,
            title=title,
            message=message,
            service="crm",
            data={
                "task_id": task_id,
                "task_type": task_type,
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


# Без broker retry: многоэтапный импорт и WS; broker retry без идемпотентности по чанкам даёт дубли сущностей/UI.
@broker.task(task_name=CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME, queue_name="crm")
async def run_knowledge_import_task(
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

    if not isinstance(row.data, dict):
        raise ValueError("task.data должен быть JSON object")
    data: dict[str, object] = row.data
    used_redis = data.get("source_text_sha256") is not None
    await _set_crm_context(
        company_id,
        row.namespace,
        auth_token,
        row.user_id,
        interface_language=interface_language,
    )
    entity_service = container.entity_service

    created_entity_ids: list[str] = []
    created_relationship_ids: list[str] = []
    notes_created = 0
    entities_from_graph = 0
    relationships_created = 0
    last_chunk_index = -1

    try:
        parts: list[str] = []
        if used_redis:
            pending = await get_pending_import_text(task_id)
            if pending and str(pending).strip():
                parts.append(str(pending).strip())
        single_id = _optional_payload_str(data, "source_file_id")
        if single_id is not None:
            parts.append((await load_text_from_stored_file_id(single_id)).strip())
        for fid in _payload_str_list(data, "source_file_ids"):
            parts.append((await load_text_from_stored_file_id(fid)).strip())
        text = "\n\n---\n\n".join(p for p in parts if p)
        if not text.strip():
            raise ValueError("Собранный текст импорта пуст")

        await repo.patch_progress(
            task_id,
            company_id,
            stage="splitting",
            progress_pct=25,
        )
        await publish_crm_task_snapshot_for_user(
            user_id=row.user_id,
            repo=repo,
            task_id=task_id,
            company_id=company_id,
        )

        chunks = split_knowledge_text(
            text,
            chunk_max_chars=_payload_int(data, "chunk_max_chars", default=50_000),
            split_by_headings=_payload_bool(data, "split_by_headings", default=False),
        )
        total_chunks = len(chunks)

        pre = await repo.get_for_worker(task_id, company_id)
        if pre is not None and pre.cancel_requested:
            await repo.patch_progress(
                task_id,
                company_id,
                status="cancelled",
                stage="cancelled",
                progress_pct=100,
                completed_at=datetime.now(timezone.utc),
            )
            await _notify_task_user(
                row.user_id,
                repo,
                company_id,
                task_id=task_id,
                task_type="knowledge_import",
                namespace=row.namespace,
                status="cancelled",
                stage="cancelled",
                progress_pct=100,
                title="Импорт отменён",
                message=f"Импорт {task_id[:8]} отменён до обработки фрагментов.",
            )
            return {"status": "cancelled", "task_id": task_id}

        await repo.patch_progress(
            task_id,
            company_id,
            stage="processing_chunks",
            progress_pct=40,
        )
        await publish_crm_task_snapshot_for_user(
            user_id=row.user_id,
            repo=repo,
            task_id=task_id,
            company_id=company_id,
        )

        async with traced_operation(
            "crm.worker.knowledge_import",
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_task",
            resource_id=task_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: row.user_id,
            },
        ):
            import_note_ids: list[str] = []
            mode = data.get("mode", "notes_only")

            for idx, chunk in enumerate(chunks):
                last_chunk_index = idx
                fresh = await repo.get_for_worker(task_id, company_id)
                if fresh is None:
                    raise RuntimeError("Строка задачи исчезла во время выполнения")
                if fresh.cancel_requested:
                    await repo.patch_progress(
                        task_id,
                        company_id,
                        status="cancelled",
                        stage="cancelled",
                        progress_pct=100,
                        completed_at=datetime.now(timezone.utc),
                        data_patch={
                            "created_entity_ids": created_entity_ids,
                            "created_relationship_ids": created_relationship_ids,
                            "notes_created_count": notes_created,
                            "entities_created_count": entities_from_graph,
                            "relationships_created_count": relationships_created,
                        },
                    )
                    await _notify_task_user(
                        row.user_id,
                        repo,
                        company_id,
                        task_id=task_id,
                        task_type="knowledge_import",
                        namespace=row.namespace,
                        status="cancelled",
                        stage="cancelled",
                        progress_pct=100,
                        title="Импорт отменён",
                        message=f"Импорт {task_id[:8]} остановлен по запросу.",
                    )
                    return {"status": "cancelled", "task_id": task_id}

                note_title = f"Импорт {task_id[:8]} #{idx + 1}"
                note = await entity_service.create_entity(
                    "note",
                    name=note_title[:500],
                    description=chunk,
                    namespace=row.namespace,
                    user_id=row.user_id,
                    note_date=datetime.now(timezone.utc).date(),
                )
                import_note_ids.append(note.entity_id)
                created_entity_ids.append(note.entity_id)
                notes_created += 1

                chunk_pct = 40 + int(40 * (idx + 1) / max(total_chunks, 1))
                await repo.patch_progress(
                    task_id,
                    company_id,
                    stage="processing_chunks",
                    progress_pct=min(chunk_pct, 80),
                    data_patch={
                        "notes_created_count": notes_created,
                        "entities_created_count": entities_from_graph,
                        "relationships_created_count": relationships_created,
                        "created_entity_ids": list(created_entity_ids),
                        "created_relationship_ids": list(created_relationship_ids),
                    },
                )
                await publish_crm_task_snapshot_for_user(
                    user_id=row.user_id,
                    repo=repo,
                    task_id=task_id,
                    company_id=company_id,
                )

            if mode == "graph":
                pipeline = container.note_processing_service
                graph_config = NoteProcessingConfig(
                    extract_entity_types=_optional_payload_str_list(data, "extract_entity_types"),
                )

                for idx, note_id in enumerate(import_note_ids):
                    last_chunk_index = idx
                    fresh = await repo.get_for_worker(task_id, company_id)
                    if fresh is None:
                        raise RuntimeError("Строка задачи исчезла во время выполнения")
                    if fresh.cancel_requested:
                        await repo.patch_progress(
                            task_id,
                            company_id,
                            status="cancelled",
                            stage="cancelled",
                            progress_pct=100,
                            completed_at=datetime.now(timezone.utc),
                            data_patch={
                                "created_entity_ids": created_entity_ids,
                                "created_relationship_ids": created_relationship_ids,
                                "notes_created_count": notes_created,
                                "entities_created_count": entities_from_graph,
                                "relationships_created_count": relationships_created,
                            },
                        )
                        await _notify_task_user(
                            row.user_id,
                            repo,
                            company_id,
                            task_id=task_id,
                            task_type="knowledge_import",
                            namespace=row.namespace,
                            status="cancelled",
                            stage="cancelled",
                            progress_pct=100,
                            title="Импорт отменён",
                            message=f"Импорт {task_id[:8]} остановлен по запросу.",
                        )
                        return {"status": "cancelled", "task_id": task_id}

                    result = await pipeline.process(note_id, graph_config)

                    for eid in result.created_entity_ids:
                        if eid not in created_entity_ids:
                            created_entity_ids.append(eid)
                    entities_from_graph += len(result.created_entity_ids) + len(
                        result.updated_entity_ids
                    )
                    for rid in result.created_relationship_ids:
                        if rid not in created_relationship_ids:
                            created_relationship_ids.append(rid)
                    relationships_created += len(result.created_relationship_ids)

                    graph_pct = 80 + int(15 * (idx + 1) / max(len(import_note_ids), 1))
                    await repo.patch_progress(
                        task_id,
                        company_id,
                        stage="processing_chunks",
                        progress_pct=min(graph_pct, 95),
                        data_patch={
                            "notes_created_count": notes_created,
                            "entities_created_count": entities_from_graph,
                            "relationships_created_count": relationships_created,
                            "created_entity_ids": list(created_entity_ids),
                            "created_relationship_ids": list(created_relationship_ids),
                        },
                    )
                    await publish_crm_task_snapshot_for_user(
                        user_id=row.user_id,
                        repo=repo,
                        task_id=task_id,
                        company_id=company_id,
                    )

        await repo.patch_progress(
            task_id,
            company_id,
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
            data_patch={
                "notes_created_count": notes_created,
                "entities_created_count": entities_from_graph,
                "relationships_created_count": relationships_created,
                "created_entity_ids": created_entity_ids,
                "created_relationship_ids": created_relationship_ids,
            },
        )
        await _notify_task_user(
            row.user_id,
            repo,
            company_id,
            task_id=task_id,
            task_type="knowledge_import",
            namespace=row.namespace,
            status="completed",
            stage="completed",
            progress_pct=100,
            title="Импорт завершён",
            message=f"Заметок: {notes_created}, сущностей: {entities_from_graph}, связей: {relationships_created}.",
        )
        return {
            "status": "completed",
            "task_id": task_id,
            "notes_created": notes_created,
            "entities_created": entities_from_graph,
            "relationships_created": relationships_created,
        }
    except Exception as exc:
        err_text = str(exc)
        logger.exception("knowledge_import failed task_id=%s", task_id)
        await repo.patch_progress(
            task_id,
            company_id,
            status="failed",
            stage="failed",
            progress_pct=100,
            completed_at=datetime.now(timezone.utc),
            error_message=err_text,
            data_patch={
                "chunk_errors": [{"chunk_index": last_chunk_index, "error": err_text}],
                "notes_created_count": notes_created,
                "entities_created_count": entities_from_graph,
                "relationships_created_count": relationships_created,
                "created_entity_ids": created_entity_ids,
                "created_relationship_ids": created_relationship_ids,
            },
        )
        await _notify_task_user(
            row.user_id,
            repo,
            company_id,
            task_id=task_id,
            task_type="knowledge_import",
            namespace=row.namespace,
            status="failed",
            stage="failed",
            progress_pct=100,
            title="Импорт с ошибкой",
            message=err_text[:500],
        )
        raise
    finally:
        if used_redis:
            await delete_pending_import_text(task_id)
