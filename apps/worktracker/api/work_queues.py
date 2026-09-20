"""REST API очередей задач — тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.realtime.operations import (
    WorkQueueIdPayload,
    WorkQueueMemberAddPayload,
    WorkQueueMemberRemovePayload,
    WorkQueuesListPayload,
    WorkQueueUpdatePayload,
    op_work_queues_create,
    op_work_queues_delete,
    op_work_queues_list,
    op_work_queues_member_add,
    op_work_queues_member_remove,
    op_work_queues_members_list,
    op_work_queues_update,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.worktracker.models import WorkQueue, WorkQueueMember
from core.worktracker.requests import (
    WorkQueueCreateRequest,
    WorkQueueMemberAddRequest,
    WorkQueueMemberRemoveRequest,
    WorkQueueMembersList,
    WorkQueueUpdateRequest,
)

router = APIRouter(prefix="/work-queues", tags=["work-queues"])


@router.get("", response_model=OffsetPage[WorkQueue])
async def list_queues(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkQueue]:
    return await op_work_queues_list(
        WorkQueuesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=WorkQueue, status_code=201)
async def create_queue(container: ContainerDep, body: WorkQueueCreateRequest) -> WorkQueue:
    return await op_work_queues_create(
        body, user=require_context().user, container=container
    )


@router.patch("/{work_queue_id}", response_model=WorkQueue)
async def update_queue(
    container: ContainerDep, work_queue_id: str, body: WorkQueueUpdateRequest
) -> WorkQueue:
    return await op_work_queues_update(
        WorkQueueUpdatePayload(
            work_queue_id=work_queue_id,
            name=body.name,
            description=body.description,
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/{work_queue_id}", status_code=204)
async def delete_queue(container: ContainerDep, work_queue_id: str) -> None:
    await op_work_queues_delete(
        WorkQueueIdPayload(work_queue_id=work_queue_id),
        user=require_context().user,
        container=container,
    )


@router.get("/{work_queue_id}/members", response_model=WorkQueueMembersList)
async def list_members(container: ContainerDep, work_queue_id: str) -> WorkQueueMembersList:
    return await op_work_queues_members_list(
        WorkQueueIdPayload(work_queue_id=work_queue_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_queue_id}/members", response_model=WorkQueueMember, status_code=201)
async def add_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberAddRequest
) -> WorkQueueMember:
    return await op_work_queues_member_add(
        WorkQueueMemberAddPayload(
            work_queue_id=work_queue_id,
            member=body.member,
            role=body.role,
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_queue_id}/members/remove", status_code=204)
async def remove_member(
    container: ContainerDep, work_queue_id: str, body: WorkQueueMemberRemoveRequest
) -> None:
    await op_work_queues_member_remove(
        WorkQueueMemberRemovePayload(work_queue_id=work_queue_id, member=body.member),
        user=require_context().user,
        container=container,
    )
