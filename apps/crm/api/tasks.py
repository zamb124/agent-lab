"""
API единого журнала задач CRM (crm_tasks).

Объединяет запуск/просмотр импорта знаний и анализа заметок.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    StartDailySummaryRequest,
    StartKnowledgeImportRequest,
    StartNoteAnalyzeRequest,
    StartPeriodSummaryRequest,
    StructuredKnowledgeImportRequest,
    TaskCreatedEntitiesResponse,
    TaskResponse,
)
from apps.crm.services.task_service import ActiveTaskExistsError
from core.pagination import OffsetPage

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _to_response(row) -> TaskResponse:
    return TaskResponse.model_validate(row)


def _active_task_conflict(exc: ActiveTaskExistsError) -> HTTPException:
    detail: dict = {
        "code": "active_task_exists",
        "message": str(exc),
        "task_type": exc.task_type,
        "task_id": exc.existing_task_id,
    }
    if exc.dedup:
        detail["dedup"] = exc.dedup
    return HTTPException(status_code=409, detail=detail)


@router.post("/knowledge-import", status_code=202, response_model=TaskResponse)
async def start_knowledge_import(
    body: StartKnowledgeImportRequest,
    container: ContainerDep,
) -> TaskResponse:
    """Запустить импорт знаний. Возвращает 202 с task_id для отслеживания прогресса."""
    try:
        row = await container.task_service.start_knowledge_import(
            namespace=body.namespace,
            mode=body.mode,
            source_file_id=body.source_file_id,
            source_file_ids=body.source_file_ids,
            source_text=body.source_text,
            extract_entity_types=body.extract_entity_types,
            split_by_headings=body.split_by_headings,
            chunk_max_chars=body.chunk_max_chars,
        )
    except ActiveTaskExistsError as exc:
        raise _active_task_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/note-analyze", status_code=202, response_model=TaskResponse)
async def start_note_analyze(
    body: StartNoteAnalyzeRequest,
    container: ContainerDep,
) -> TaskResponse:
    """Запустить анализ заметки. Возвращает 202 с task_id для отслеживания прогресса через WebSocket."""
    from apps.crm.models.api import NoteProcessingConfig
    from core.context import get_context

    note = await container.entity_service.get_entity(body.note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Заметка не найдена")

    ctx = get_context()
    user_id = ctx.user.user_id if ctx and ctx.user else None
    company_id = ctx.active_company.company_id if ctx and ctx.active_company else None
    if not user_id or not company_id:
        raise HTTPException(status_code=500, detail="Контекст пользователя или компании отсутствует")
    if not await container.access_control_service.can_write_entity(note, user_id, company_id):
        raise HTTPException(status_code=403, detail="Access denied")

    config = NoteProcessingConfig(
        include_attachments=body.include_attachments,
        attachment_chars_limit_per_file=body.attachment_chars_limit_per_file,
        check_duplicates=body.check_duplicates,
        extract_entity_types=body.extract_entity_types,
        extract_relationship_types=body.extract_relationship_types,
        mentioned_entity_ids=body.mentioned_entity_ids,
    )
    ns = note.namespace or "default"

    try:
        row = await container.task_service.start_note_analyze(
            note_id=body.note_id,
            note_name=note.name or "",
            namespace=ns,
            mode=body.mode,
            config=config,
        )
    except ActiveTaskExistsError as exc:
        raise _active_task_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.get("", response_model=OffsetPage[TaskResponse])
async def list_tasks(
    container: ContainerDep,
    namespace: Optional[str] = Query(None, description="Фильтр по пространству; пусто = все пространства компании"),
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    note_id: Optional[str] = Query(None, description="Фильтр по note_id внутри data (только note_analyze)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage[TaskResponse]:
    rows, total = await asyncio.gather(
        container.task_service.list_tasks(namespace, task_type=task_type, note_id=note_id, limit=limit, offset=offset),
        container.task_service.count_tasks(namespace, task_type=task_type, note_id=note_id),
    )
    return OffsetPage[TaskResponse](items=[_to_response(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, container: ContainerDep) -> TaskResponse:
    row = await container.task_service.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return _to_response(row)


@router.get("/{task_id}/created-entities", response_model=TaskCreatedEntitiesResponse)
async def get_task_created_entities(
    task_id: str,
    container: ContainerDep,
) -> TaskCreatedEntitiesResponse:
    try:
        return await container.task_service.get_task_created_entities(task_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Задача не найдена") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/review-complete", response_model=TaskResponse)
async def complete_task_review(task_id: str, container: ContainerDep) -> TaskResponse:
    try:
        row = await container.task_service.complete_task_review(task_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Задача не найдена") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str, container: ContainerDep) -> TaskResponse:
    try:
        row = await container.task_service.request_cancel(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/rollback", response_model=TaskResponse)
async def rollback_task(task_id: str, container: ContainerDep) -> TaskResponse:
    try:
        row = await container.task_service.rollback_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/daily-summary", status_code=202, response_model=TaskResponse)
async def start_daily_summary(
    body: StartDailySummaryRequest,
    container: ContainerDep,
) -> TaskResponse:
    """Запустить пересчёт дневной сводки. Возвращает 202 с task_id."""
    try:
        row = await container.task_service.start_daily_summary(
            namespace=body.namespace,
            date_str=body.date_str,
            reason=body.reason,
        )
    except ActiveTaskExistsError as exc:
        raise _active_task_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/period-summary", status_code=202, response_model=TaskResponse)
async def start_period_summary(
    body: StartPeriodSummaryRequest,
    container: ContainerDep,
) -> TaskResponse:
    """Запустить пересчёт сводки за период. Возвращает 202 с task_id."""
    try:
        row = await container.task_service.start_period_summary(
            namespace=body.namespace,
            date_from=body.date_from,
            date_to=body.date_to,
            reason=body.reason,
        )
    except ActiveTaskExistsError as exc:
        raise _active_task_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{task_id}/retry", status_code=202, response_model=TaskResponse)
async def retry_task(task_id: str, container: ContainerDep) -> TaskResponse:
    """Перезапустить failed/cancelled задачу с теми же параметрами."""
    try:
        row = await container.task_service.retry_task(task_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Задача не найдена") from None
    except ActiveTaskExistsError as exc:
        raise _active_task_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/structured/bulk")
async def structured_knowledge_import_not_implemented(
    _body: StructuredKnowledgeImportRequest,
    container: ContainerDep,
) -> None:
    raise HTTPException(
        status_code=501,
        detail="Структурированный импорт (bulk без LLM) в этой версии не реализован.",
    )
