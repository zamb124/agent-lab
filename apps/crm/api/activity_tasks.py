"""CRM activity-tasks: атомарная пара CRMEntity(task) + WorkItem(crm_activity)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import EntityResponse
from apps.crm.services.entity_response_enrichment import (
    build_entity_responses_with_semantic_index,
)
from core.context import get_context
from core.pagination import OffsetPage
from core.worktracker.models import WorkItem, WorkItemKind, WorkItemState

router = APIRouter(prefix="/activity-tasks", tags=["activity-tasks"])


class ActivityTaskCreateRequest(BaseModel):
    """Создание пары графовый узел task + WorkItem(crm_activity)."""

    title: str = Field(..., min_length=1)
    description: str | None = None
    namespace: str = Field(default="default", min_length=1)
    entity_subtype: str | None = None
    priority: str | None = None
    due_date: date | None = None
    assignees: list[str] | None = None
    tags: list[str] | None = None


class ActivityTaskResponse(BaseModel):
    """Ответ create: CRM-узел + парный WorkItem."""

    entity: EntityResponse
    work_item: WorkItem


@router.post("", response_model=ActivityTaskResponse)
async def create_activity_task(
    body: ActivityTaskCreateRequest,
    container: ContainerDep,
) -> ActivityTaskResponse:
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=401, detail="Требуется аутентификация")
    user_id = ctx.user.user_id

    entity = await container.entity_service.create_entity(
        entity_type="task",
        name=body.title,
        description=body.description,
        entity_subtype=body.entity_subtype,
        tags=body.tags,
        namespace=body.namespace,
        user_id=user_id,
        priority=body.priority,
        due_date=body.due_date,
        assignees=body.assignees,
    )
    work_item = await container.crm_work_item_service.get_for_task(
        company_id=entity.company_id,
        entity_id=entity.entity_id,
    )
    if work_item is None:
        raise HTTPException(
            status_code=500,
            detail="Парный WorkItem не создан для CRM-задачи",
        )
    entities = await build_entity_responses_with_semantic_index(
        container.entity_repository,
        [entity],
        crm_work_item_service=container.crm_work_item_service,
    )
    return ActivityTaskResponse(entity=entities[0], work_item=work_item)


@router.get("", response_model=OffsetPage[WorkItem])
async def list_activity_tasks(
    container: ContainerDep,
    namespace: str | None = None,
    state: WorkItemState | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkItem]:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Требуется аутентификация")
    company_id = ctx.active_company.company_id
    items = await container.crm_work_item_service.list_crm_activity_work_items(
        company_id=company_id,
        namespace=namespace,
        state=state,
        limit=limit,
        offset=offset,
    )
    total = await container.work_item_service.count(
        company_id,
        namespace=namespace,
        kind=WorkItemKind.CRM_ACTIVITY,
        state=state,
    )
    return OffsetPage[WorkItem](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
