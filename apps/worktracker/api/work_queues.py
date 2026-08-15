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
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.pagination import OffsetPage
from core.worktracker.models import WorkQueue, WorkQueueMember

router = APIRouter(prefix="/work-queues", tags=["work-queues"])


def _actor_user_id() -> str:
    return current_user_actor().user_id


@router.get("", response_model=OffsetPage[WorkQueue])
async def list_queues(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkQueue]:
    items = await container.work_item_service.list_queues(
        current_company_id(), user_id=_actor_user_id()
    )
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
            actor_user_id=_actor_user_id(),
        )
    except AuthzDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{work_queue_id}", status_code=204)
async def delete_queue(container: ContainerDep, work_queue_id: str) -> None:
    try:
        await container.work_item_service.delete_queue(
            company_id=current_company_id(),
            work_queue_id=work_queue_id,
            actor_user_id=_actor_user_id(),
        )
    except AuthzDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{work_queue_id}/members", response_model=list[WorkQueueMember])
async def list_members(container: ContainerDep, work_queue_id: str) -> list[WorkQueueMember]:
    try:
        await container.authz_service.require_can_view(
            AuthzObject.work_queue(work_queue_id), user_id=_actor_user_id()
        )
    except AuthzDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return await container.work_item_service.list_queue_members(work_queue_id)


@router.post("/{work_queue_id}/members", response_model=WorkQueueMember, status_code=201)
async def add_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberAddRequest
) -> WorkQueueMember:
    try:
        return await container.work_item_service.add_queue_member(
            company_id=current_company_id(),
            work_queue_id=work_queue_id,
            member=body.member,
            role=body.role,
            actor_user_id=_actor_user_id(),
        )
    except AuthzDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{work_queue_id}/members/remove", status_code=204)
async def remove_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberRemoveRequest
) -> None:
    try:
        removed = await container.work_item_service.remove_queue_member(
            work_queue_id=work_queue_id,
            member=body.member,
            actor_user_id=_actor_user_id(),
        )
    except AuthzDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Участник очереди не найден")
