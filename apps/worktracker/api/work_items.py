"""REST API задач WorkItem (зеркало WS-команд worktracker/work_item/*)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.worktracker.api._common import (
    current_company_id,
    current_user_actor,
    current_user_id,
)
from apps.worktracker.dependencies import ContainerDep
from apps.worktracker.models.api import (
    WorkItemAssignRequest,
    WorkItemCommentRequest,
    WorkItemCompleteRequest,
    WorkItemCreateRequest,
    WorkItemMineSummaryResponse,
    WorkItemMoveRequest,
    WorkItemUpdateRequest,
)
from core.pagination import OffsetPage
from core.worktracker.models import (
    WorkItem,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemKind,
    WorkItemResolution,
    WorkItemState,
)

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
    company_id = current_company_id()
    service = container.work_item_service
    items = await service.list(
        company_id,
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
    )
    total = await service.count(
        company_id,
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
    )
    return OffsetPage[WorkItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/mine/summary", response_model=WorkItemMineSummaryResponse)
async def mine_work_items_summary(container: ContainerDep) -> WorkItemMineSummaryResponse:
    summary = await container.work_item_service.mine_summary(
        current_company_id(),
        current_user_id(),
    )
    return WorkItemMineSummaryResponse(
        assigned_open_count=summary.assigned_open_count,
        queue_inbox_count=summary.queue_inbox_count,
    )


@router.get("/{work_item_id}", response_model=WorkItem)
async def get_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    try:
        return await container.work_item_service.get(current_company_id(), work_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=WorkItem, status_code=201)
async def create_work_item(container: ContainerDep, body: WorkItemCreateRequest) -> WorkItem:
    actor = current_user_actor()
    if body.assignment is not None:
        return await container.work_item_service.create(
            company_id=current_company_id(),
            title=body.title,
            created_by=actor,
            description=body.description,
            kind=body.kind,
            namespace=body.namespace,
            board_id=body.board_id,
            board_column_id=body.board_column_id,
            priority=body.priority,
            due_date=body.due_date,
            labels=body.labels,
            assignment=body.assignment,
            blocking=body.blocking,
            links=body.links,
            variables=body.variables,
            attachments=body.attachments,
        )
    return await container.work_item_service.create_manual_task(
        company_id=current_company_id(),
        title=body.title,
        created_by=actor,
        description=body.description,
        kind=body.kind,
        namespace=body.namespace,
        board_id=body.board_id,
        board_column_id=body.board_column_id,
        priority=body.priority,
        due_date=body.due_date,
        labels=body.labels,
        blocking=body.blocking,
        links=body.links,
        variables=body.variables,
        attachments=body.attachments,
    )


@router.patch("/{work_item_id}", response_model=WorkItem)
async def update_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemUpdateRequest
) -> WorkItem:
    try:
        return await container.work_item_service.update(
            company_id=current_company_id(),
            work_item_id=work_item_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            due_date=body.due_date,
            labels=body.labels,
            links=body.links,
            variables=body.variables,
            attachments=body.attachments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{work_item_id}/assign", response_model=WorkItem)
async def assign_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemAssignRequest
) -> WorkItem:
    """Переназначить задачу (человек/очередь/агент) — для любого вида задач."""
    try:
        return await container.work_item_service.reassign(
            company_id=current_company_id(),
            work_item_id=work_item_id,
            assignment=body.assignment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{work_item_id}/move", response_model=WorkItem)
async def move_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemMoveRequest
) -> WorkItem:
    try:
        return await container.work_item_service.move(
            company_id=current_company_id(),
            work_item_id=work_item_id,
            board_column_id=body.board_column_id,
            state=body.state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{work_item_id}/claim", response_model=WorkItem)
async def claim_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    try:
        return await container.work_item_service.claim(
            company_id=current_company_id(),
            work_item_id=work_item_id,
            user_id=current_user_id(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{work_item_id}/comments", response_model=WorkItemComment, status_code=201)
async def add_comment(
    container: ContainerDep, work_item_id: str, body: WorkItemCommentRequest
) -> WorkItemComment:
    try:
        return await container.work_item_service.add_comment(
            company_id=current_company_id(),
            work_item_id=work_item_id,
            author=current_user_actor(),
            role=WorkItemCommentRole.OPERATOR,
            text=body.text,
            files=body.files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{work_item_id}/comments", response_model=list[WorkItemComment])
async def list_comments(container: ContainerDep, work_item_id: str) -> list[WorkItemComment]:
    return await container.work_item_service.list_comments(current_company_id(), work_item_id)


@router.post("/{work_item_id}/complete", response_model=WorkItem)
async def complete_work_item(
    container: ContainerDep, work_item_id: str, body: WorkItemCompleteRequest
) -> WorkItem:
    company_id = current_company_id()
    resolution = WorkItemResolution(
        text=body.resolution_text,
        files=body.resolution_files,
        resolved_by=current_user_actor(),
    )
    try:
        completion = await container.work_item_service.complete(
            company_id=company_id,
            work_item_id=work_item_id,
            resolution=resolution,
            terminal_state=body.terminal_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return completion.work_item


@router.post("/{work_item_id}/cancel", response_model=WorkItem)
async def cancel_work_item(container: ContainerDep, work_item_id: str) -> WorkItem:
    try:
        completion = await container.work_item_service.cancel(
            company_id=current_company_id(),
            work_item_id=work_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return completion.work_item
