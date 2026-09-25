"""REST API очередей задач — тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.worktracker.di import Di
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
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkQueue]:
    return await op_work_queues_list(
        WorkQueuesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.post("", response_model=WorkQueue, status_code=201)
async def create_queue(di: Di, body: WorkQueueCreateRequest) -> WorkQueue:
    return await op_work_queues_create(
        body, user=require_context().user, di=di
    )


@router.patch("/{work_queue_id}", response_model=WorkQueue)
async def update_queue(
    di: Di, work_queue_id: str, body: WorkQueueUpdateRequest
) -> WorkQueue:
    return await op_work_queues_update(
        WorkQueueUpdatePayload(
            work_queue_id=work_queue_id,
            name=body.name,
            description=body.description,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{work_queue_id}", status_code=204)
async def delete_queue(di: Di, work_queue_id: str) -> None:
    await op_work_queues_delete(
        WorkQueueIdPayload(work_queue_id=work_queue_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{work_queue_id}/members", response_model=WorkQueueMembersList)
async def list_members(di: Di, work_queue_id: str) -> WorkQueueMembersList:
    return await op_work_queues_members_list(
        WorkQueueIdPayload(work_queue_id=work_queue_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{work_queue_id}/members", response_model=WorkQueueMember, status_code=201)
async def add_member(
    di: Di, work_queue_id: str, body: WorkQueueMemberAddRequest
) -> WorkQueueMember:
    return await op_work_queues_member_add(
        WorkQueueMemberAddPayload(
            work_queue_id=work_queue_id,
            member=body.member,
            role=body.role,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{work_queue_id}/members/remove", status_code=204)
async def remove_member(
    di: Di, work_queue_id: str, body: WorkQueueMemberRemoveRequest
) -> None:
    await op_work_queues_member_remove(
        WorkQueueMemberRemovePayload(work_queue_id=work_queue_id, member=body.member),
        user=require_context().user,
        di=di,
    )
