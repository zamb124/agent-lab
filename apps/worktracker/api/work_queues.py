"""REST API очередей задач (зеркало WS-команд worktracker/work_queue/*)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.worktracker.api._common import current_company_id, current_user_actor
from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.models.api import (
    WorkQueueCreateRequest,
    WorkQueueMemberAddRequest,
    WorkQueueMemberRemoveRequest,
    WorkQueueUpdateRequest,
)
from core.pagination import OffsetPage
from core.worktracker.models import WorkQueue, WorkQueueMember

router = APIRouter(prefix="/work-queues", tags=["work-queues"])


@router.get("", response_model=OffsetPage[WorkQueue])
async def list_queues(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkQueue]:
    items = await container.work_item_service.list_queues(current_company_id())
    total = len(items)
    page_items = items[offset : offset + limit]
    return OffsetPage[WorkQueue](items=page_items, total=total, limit=limit, offset=offset)


@router.post("", response_model=WorkQueue, status_code=201)
async def create_queue(container: ContainerDep, body: WorkQueueCreateRequest) -> WorkQueue:
    try:
        return await container.work_item_service.create_queue(
            company_id=current_company_id(),
            name=body.name,
            slug=body.slug,
            description=body.description,
            creator=current_user_actor(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{work_queue_id}", response_model=WorkQueue)
async def update_queue(
    container: ContainerDep, work_queue_id: str, body: WorkQueueUpdateRequest
) -> WorkQueue:
    try:
        return await container.work_item_service.update_queue(
            company_id=current_company_id(),
            work_queue_id=work_queue_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{work_queue_id}/members", response_model=list[WorkQueueMember])
async def list_members(container: ContainerDep, work_queue_id: str) -> list[WorkQueueMember]:
    return await container.work_item_service.list_queue_members(work_queue_id)


@router.post("/{work_queue_id}/members", response_model=WorkQueueMember, status_code=201)
async def add_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberAddRequest
) -> WorkQueueMember:
    return await container.work_item_service.add_queue_member(
        company_id=current_company_id(),
        work_queue_id=work_queue_id,
        member=body.member,
        role=body.role,
    )


@router.post("/{work_queue_id}/members/remove", status_code=204)
async def remove_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberRemoveRequest
) -> None:
    removed = await container.work_item_service.remove_queue_member(
        work_queue_id=work_queue_id, member=body.member
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Участник очереди не найден")
