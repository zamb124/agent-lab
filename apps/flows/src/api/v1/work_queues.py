"""REST API очередей WorkQueue для редактора hitl_node (list + create).

Источник данных — тот же WorkItemService / БД platform_worktracker, что и
worktracker API. Тонкое зеркало нужно flows SPA (REST-зеркало фабрики
`flows/work_queues`) без кросс-импорта UI worktracker.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from core.context import require_active_company, require_context
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.worktracker.models import UserActor, WorkQueue

router = APIRouter(prefix="/work-queues", tags=["work-queues"])


class WorkQueueCreateBody(StrictBaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    description: str | None = None


@router.get("", response_model=OffsetPage[WorkQueue])
async def list_queues(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkQueue]:
    company_id = require_active_company().company_id
    items = await container.work_item_service.list_queues(company_id)
    total = len(items)
    page_items = items[offset : offset + limit]
    return OffsetPage[WorkQueue](items=page_items, total=total, limit=limit, offset=offset)


@router.post("", response_model=WorkQueue, status_code=201)
async def create_queue(container: ContainerDep, body: WorkQueueCreateBody) -> WorkQueue:
    company_id = require_active_company().company_id
    creator = UserActor(user_id=require_context().user.user_id)
    try:
        return await container.work_item_service.create_queue(
            company_id=company_id,
            name=body.name,
            slug=body.slug,
            description=body.description,
            creator=creator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
