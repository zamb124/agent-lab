"""REST API задач WorkItem — тонкая обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.models.api import (
    WorkItemAssignRequest,
    WorkItemCommentRequest,
    WorkItemCommentsList,
    WorkItemCompleteRequest,
    WorkItemCreateRequest,
    WorkItemMoveRequest,
    WorkItemUpdateRequest,
)
from apps.worktracker.realtime.operations import (
    WorkItemAssignPayload,
    WorkItemCommentPayload,
    WorkItemCompletePayload,
    WorkItemIdPayload,
    WorkItemMovePayload,
    WorkItemsListPayload,
    WorkItemsMineSummaryPayload,
    WorkItemUpdatePayload,
    op_work_items_assign,
    op_work_items_cancel,
    op_work_items_claim,
    op_work_items_comment,
    op_work_items_comments_list,
    op_work_items_complete,
    op_work_items_create,
    op_work_items_get,
    op_work_items_list,
    op_work_items_mine_summary,
    op_work_items_move,
    op_work_items_update,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.worktracker.models import WorkItem, WorkItemComment, WorkItemKind, WorkItemState
from core.worktracker.service import WorkItemMineSummary

router = APIRouter(prefix="/work-items", tags=["work-items"])


@router.get("", response_model=OffsetPage[WorkItem])
async def list_work_items(
    container: ContainerDep,
    board_id: Annotated[str | None, Query()] = None,
    namespace: Annotated[str | None, Query()] = None,
    kind: Annotated[WorkItemKind | None, Query()] = None,
    state: Annotated[WorkItemState | None, Query()] = None,
    work_queue_id: Annotated[str | None, Query()] = None,
    assignee_user_id: Annotated[str | None, Query()] = None,
    assignee_flow_id: Annotated[str | None, Query()] = None,
    exclude_terminal: Annotated[bool, Query()] = False,
    queue_unclaimed_only: Annotated[bool, Query()] = False,
    work_queue_ids: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[WorkItem]:
    return await op_work_items_list(
        WorkItemsListPayload(
            board_id=board_id,
            namespace=namespace,
            kind=kind,
            state=state,
            work_queue_id=work_queue_id,
            assignee_user_id=assignee_user_id,
            assignee_flow_id=assignee_flow_id,
            exclude_terminal=exclude_terminal,
            queue_unclaimed_only=queue_unclaimed_only,
            work_queue_ids=work_queue_ids,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/mine/summary", response_model=WorkItemMineSummary)
async def mine_work_items_summary(container: ContainerDep) -> WorkItemMineSummary:
    return await op_work_items_mine_summary(
        WorkItemsMineSummaryPayload(),
        user=require_context().user,
        container=container,
    )


@router.get("/{work_item_id}", response_model=WorkItem)
async def get_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    return await op_work_items_get(
        WorkItemIdPayload(work_item_id=work_item_id),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=WorkItem, status_code=201)
async def create_work_item(container: ContainerDep, body: WorkItemCreateRequest) -> WorkItem:
    return await op_work_items_create(
        body, user=require_context().user, container=container
    )


@router.patch("/{work_item_id}", response_model=WorkItem)
async def update_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemUpdateRequest
) -> WorkItem:
    return await op_work_items_update(
        WorkItemUpdatePayload(
            work_item_id=work_item_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            due_date=body.due_date,
            labels=body.labels,
            links=body.links,
            variables=body.variables,
            attachments=body.attachments,
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/assign", response_model=WorkItem)
async def assign_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemAssignRequest
) -> WorkItem:
    return await op_work_items_assign(
        WorkItemAssignPayload(work_item_id=work_item_id, assignment=body.assignment),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/move", response_model=WorkItem)
async def move_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemMoveRequest
) -> WorkItem:
    return await op_work_items_move(
        WorkItemMovePayload(
            work_item_id=work_item_id,
            board_column_id=body.board_column_id,
            state=body.state,
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/claim", response_model=WorkItem)
async def claim_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    return await op_work_items_claim(
        WorkItemIdPayload(work_item_id=work_item_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/comments", response_model=WorkItemComment, status_code=201)
async def add_comment(
    container: ContainerDep, work_item_id: str, body: WorkItemCommentRequest
) -> WorkItemComment:
    return await op_work_items_comment(
        WorkItemCommentPayload(
            work_item_id=work_item_id,
            text=body.text,
            files=body.files,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/{work_item_id}/comments", response_model=WorkItemCommentsList)
async def list_comments(container: ContainerDep, work_item_id: str) -> WorkItemCommentsList:
    return await op_work_items_comments_list(
        WorkItemIdPayload(work_item_id=work_item_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/complete", response_model=WorkItem)
async def complete_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemCompleteRequest
) -> WorkItem:
    return await op_work_items_complete(
        WorkItemCompletePayload(
            work_item_id=work_item_id,
            resolution_text=body.resolution_text,
            resolution_files=body.resolution_files,
            terminal_state=body.terminal_state,
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/{work_item_id}/cancel", response_model=WorkItem)
async def cancel_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    return await op_work_items_cancel(
        WorkItemIdPayload(work_item_id=work_item_id),
        user=require_context().user,
        container=container,
    )
