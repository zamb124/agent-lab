"""
TaskIQ: импорт базы знаний.

Пайплайн: (1) нарезка текста → создание сущностей note (как при ручной заметке);
(2) при mode=graph — для каждой такой note тот же путь, что у analyze заметки:
analyze_text_with_ai + apply_analysis_draft. Режим notes_only — только фаза 1.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from apps.crm.container import get_crm_container
from apps.crm.models.api import AIAnalyzeRequest
from apps.crm.services.knowledge_import_source_loader import load_text_from_stored_file_id
from apps.crm.services.knowledge_import_text_redis import (
    delete_pending_import_text,
    get_pending_import_text,
)
from apps.crm_worker.broker import broker
from apps.crm_worker.tasks.daily_summary_tasks import _set_crm_context
from core.logging import get_logger
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation
from core.utils.knowledge_text_split import split_knowledge_text
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


async def _notify_import_user(
    user_id: str,
    *,
    import_id: str,
    namespace: str,
    status: str,
    title: str,
    message: str,
) -> None:
    await notify_user(
        user_id,
        Notification(
            type=NotificationType.CRM_KNOWLEDGE_IMPORT_UPDATED,
            title=title,
            message=message,
            service="crm",
            data={
                "import_id": import_id,
                "namespace": namespace,
                "status": status,
            },
        ),
    )


@broker.task
async def run_knowledge_import_task(
    import_id: str,
    company_id: str,
    auth_token: Optional[str],
) -> dict[str, Any]:
    container = get_crm_container()
    repo = container.knowledge_import_repository
    row = await repo.get_for_worker(import_id, company_id)
    if row is None:
        raise ValueError(f"Импорт не найден: {import_id}")

    used_redis = row.source_text_sha256 is not None
    _set_crm_context(company_id, row.namespace, auth_token, row.user_id)
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
            pending = await get_pending_import_text(import_id)
            if pending and str(pending).strip():
                parts.append(str(pending).strip())
        single_id = str(row.source_file_id).strip() if row.source_file_id else ""
        if single_id:
            parts.append((await load_text_from_stored_file_id(single_id)).strip())
        multi_ids = row.source_file_ids if isinstance(row.source_file_ids, list) else []
        for fid in multi_ids:
            s = str(fid).strip()
            if s:
                parts.append((await load_text_from_stored_file_id(s)).strip())
        text = "\n\n---\n\n".join(p for p in parts if p)
        if not text.strip():
            raise ValueError("Собранный текст импорта пуст")

        chunks = split_knowledge_text(
            text,
            chunk_max_chars=row.chunk_max_chars,
            split_by_headings=row.split_by_headings,
        )

        pre = await repo.get_for_worker(import_id, company_id)
        if pre is not None and pre.cancel_requested:
            await repo.patch_progress(
                import_id,
                company_id,
                status="cancelled",
                completed_at=datetime.now(timezone.utc),
            )
            await _notify_import_user(
                row.user_id,
                import_id=import_id,
                namespace=row.namespace,
                status="cancelled",
                title="Импорт отменён",
                message=f"Импорт {import_id} отменён до обработки фрагментов.",
            )
            return {"status": "cancelled", "import_id": import_id}

        async with traced_operation(
            "crm.worker.knowledge_import",
            event_type="crm.worker",
            operation_category="sync_command",
            resource_type="crm_knowledge_import",
            resource_id=import_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: row.user_id,
            },
        ):
            import_note_ids: list[str] = []

            for idx, chunk in enumerate(chunks):
                last_chunk_index = idx
                fresh = await repo.get_for_worker(import_id, company_id)
                if fresh is None:
                    raise RuntimeError("Строка импорта исчезла во время выполнения")
                if fresh.cancel_requested:
                    await repo.patch_progress(
                        import_id,
                        company_id,
                        status="cancelled",
                        completed_at=datetime.now(timezone.utc),
                        created_entity_ids=created_entity_ids,
                        created_relationship_ids=created_relationship_ids,
                        notes_created_count=notes_created,
                        entities_created_count=entities_from_graph,
                        relationships_created_count=relationships_created,
                    )
                    await _notify_import_user(
                        row.user_id,
                        import_id=import_id,
                        namespace=row.namespace,
                        status="cancelled",
                        title="Импорт отменён",
                        message=f"Импорт {import_id} остановлен по запросу.",
                    )
                    return {"status": "cancelled", "import_id": import_id}

                title = f"Импорт {import_id[:8]} #{idx + 1}"
                note = await entity_service.create_entity(
                    "note",
                    name=title[:500],
                    description=chunk,
                    namespace=row.namespace,
                    user_id=row.user_id,
                    note_date=datetime.now(timezone.utc).date(),
                )
                import_note_ids.append(note.entity_id)
                created_entity_ids.append(note.entity_id)
                notes_created += 1

                await repo.patch_progress(
                    import_id,
                    company_id,
                    notes_created_count=notes_created,
                    entities_created_count=entities_from_graph,
                    relationships_created_count=relationships_created,
                    created_entity_ids=list(created_entity_ids),
                    created_relationship_ids=list(created_relationship_ids),
                )

            if row.mode == "graph":
                for idx, note_id in enumerate(import_note_ids):
                    last_chunk_index = idx
                    fresh = await repo.get_for_worker(import_id, company_id)
                    if fresh is None:
                        raise RuntimeError("Строка импорта исчезла во время выполнения")
                    if fresh.cancel_requested:
                        await repo.patch_progress(
                            import_id,
                            company_id,
                            status="cancelled",
                            completed_at=datetime.now(timezone.utc),
                            created_entity_ids=created_entity_ids,
                            created_relationship_ids=created_relationship_ids,
                            notes_created_count=notes_created,
                            entities_created_count=entities_from_graph,
                            relationships_created_count=relationships_created,
                        )
                        await _notify_import_user(
                            row.user_id,
                            import_id=import_id,
                            namespace=row.namespace,
                            status="cancelled",
                            title="Импорт отменён",
                            message=f"Импорт {import_id} остановлен по запросу.",
                        )
                        return {"status": "cancelled", "import_id": import_id}

                    note_row = await entity_service.get_entity(note_id)
                    if note_row is None:
                        raise RuntimeError(f"Заметка импорта не найдена после создания: {note_id}")
                    analyze_text = note_row.description if note_row.description else ""

                    req = AIAnalyzeRequest(
                        text=analyze_text,
                        extract_entity_types=row.extract_entity_types,
                        extract_relationship_types=None,
                        mentioned_entity_ids=None,
                        namespace=row.namespace,
                    )
                    await entity_service.analyze_text_with_ai(
                        req,
                        check_duplicates=True,
                        note_id=note_id,
                    )
                    apply_result = await entity_service.apply_analysis_draft(note_id)
                    for eid in apply_result.created_entity_ids:
                        if eid not in created_entity_ids:
                            created_entity_ids.append(eid)
                    entities_from_graph += len(apply_result.created_entity_ids)
                    for rid in apply_result.created_relationship_ids:
                        if rid not in created_relationship_ids:
                            created_relationship_ids.append(rid)
                    relationships_created += len(apply_result.created_relationship_ids)

                    await repo.patch_progress(
                        import_id,
                        company_id,
                        notes_created_count=notes_created,
                        entities_created_count=entities_from_graph,
                        relationships_created_count=relationships_created,
                        created_entity_ids=list(created_entity_ids),
                        created_relationship_ids=list(created_relationship_ids),
                    )

        await repo.patch_progress(
            import_id,
            company_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            notes_created_count=notes_created,
            entities_created_count=entities_from_graph,
            relationships_created_count=relationships_created,
            created_entity_ids=created_entity_ids,
            created_relationship_ids=created_relationship_ids,
        )
        await _notify_import_user(
            row.user_id,
            import_id=import_id,
            namespace=row.namespace,
            status="completed",
            title="Импорт завершён",
            message=f"Заметок: {notes_created}, сущностей: {entities_from_graph}, связей: {relationships_created}.",
        )
        return {
            "status": "completed",
            "import_id": import_id,
            "notes_created": notes_created,
            "entities_created": entities_from_graph,
            "relationships_created": relationships_created,
        }
    except Exception as exc:
        err_text = str(exc)
        logger.exception("knowledge_import failed import_id=%s", import_id)
        await repo.patch_progress(
            import_id,
            company_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error_message=err_text,
            chunk_errors=[{"chunk_index": last_chunk_index, "error": err_text}],
            notes_created_count=notes_created,
            entities_created_count=entities_from_graph,
            relationships_created_count=relationships_created,
            created_entity_ids=created_entity_ids,
            created_relationship_ids=created_relationship_ids,
        )
        await _notify_import_user(
            row.user_id,
            import_id=import_id,
            namespace=row.namespace,
            status="failed",
            title="Импорт с ошибкой",
            message=err_text[:500],
        )
        raise
    finally:
        if used_redis:
            await delete_pending_import_text(import_id)
