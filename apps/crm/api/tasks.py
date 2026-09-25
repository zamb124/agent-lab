"""
API единого журнала задач CRM (crm_tasks).

REST-зеркало: тот же `op_*`, что и Centrifugo RPC `platform.event`.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.di import Di
from apps.crm.models.api import (
    StartDailySummaryRequest,
    StartKnowledgeImportRequest,
    StartNoteAnalyzeRequest,
    StartPeriodSummaryRequest,
    TaskCreatedEntitiesResponse,
)
from apps.crm.models.task import CRMTask
from apps.crm.realtime.operations import (
    CrmTaskIdPayload,
    CrmTasksListPayload,
    op_notes_analyze,
    op_tasks_cancel,
    op_tasks_created_entities,
    op_tasks_daily_summary_start,
    op_tasks_item,
    op_tasks_knowledge_import_start,
    op_tasks_list,
    op_tasks_period_summary_start,
    op_tasks_retry,
    op_tasks_review_complete,
    op_tasks_rollback,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("/knowledge-import", status_code=202, response_model=CRMTask)
async def start_knowledge_import(
    body: StartKnowledgeImportRequest,
    di: Di,
) -> CRMTask:
    return await op_tasks_knowledge_import_start(
        body, user=require_context().user, di=di
    )


@router.post("/note-analyze", status_code=202, response_model=CRMTask)
async def start_note_analyze(
    body: StartNoteAnalyzeRequest,
    di: Di,
) -> CRMTask:
    return await op_notes_analyze(
        body, user=require_context().user, di=di
    )


@router.get("", response_model=OffsetPage[CRMTask])
async def list_tasks(
    di: Di,
    namespace: Annotated[
        str | None,
        Query(description="Фильтр по пространству; пусто = все пространства компании"),
    ] = None,
    task_type: Annotated[str | None, Query(description="Фильтр по типу задачи")] = None,
    note_id: Annotated[
        str | None,
        Query(description="Фильтр по note_id внутри data (только note_analyze)"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[CRMTask]:
    return await op_tasks_list(
        CrmTasksListPayload(
            namespace=namespace,
            task_type=task_type,
            note_id=note_id,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/{task_id}", response_model=CRMTask)
async def get_task(task_id: str, di: Di) -> CRMTask:
    return await op_tasks_item(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{task_id}/created-entities", response_model=TaskCreatedEntitiesResponse)
async def get_task_created_entities(
    task_id: str,
    di: Di,
) -> TaskCreatedEntitiesResponse:
    return await op_tasks_created_entities(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{task_id}/review-complete", response_model=CRMTask)
async def complete_task_review(task_id: str, di: Di) -> CRMTask:
    return await op_tasks_review_complete(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{task_id}/cancel", response_model=CRMTask)
async def cancel_task(task_id: str, di: Di) -> CRMTask:
    return await op_tasks_cancel(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{task_id}/rollback", response_model=CRMTask)
async def rollback_task(task_id: str, di: Di) -> CRMTask:
    return await op_tasks_rollback(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )


@router.post("/daily-summary", status_code=202, response_model=CRMTask)
async def start_daily_summary(
    body: StartDailySummaryRequest,
    di: Di,
) -> CRMTask:
    return await op_tasks_daily_summary_start(
        body, user=require_context().user, di=di
    )


@router.post("/period-summary", status_code=202, response_model=CRMTask)
async def start_period_summary(
    body: StartPeriodSummaryRequest,
    di: Di,
) -> CRMTask:
    return await op_tasks_period_summary_start(
        body, user=require_context().user, di=di
    )


@router.post("/{task_id}/retry", status_code=202, response_model=CRMTask)
async def retry_task(task_id: str, di: Di) -> CRMTask:
    return await op_tasks_retry(
        CrmTaskIdPayload(task_id=task_id),
        user=require_context().user,
        di=di,
    )
