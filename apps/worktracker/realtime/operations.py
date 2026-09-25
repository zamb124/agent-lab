"""Бизнес-функции worktracker: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

from apps.worktracker.di import Di
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.context import require_active_company
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import (
    WsCommandError,
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)
from core.worktracker.models import (
    Board,
    UserActor,
    WorkItem,
    WorkItemComment,
    WorkItemCommentRole,
    WorkItemKind,
    WorkItemResolution,
    WorkItemState,
    WorkQueue,
    WorkQueueMember,
    WorktrackerModel,
    build_interaction_policy,
)
from core.worktracker.requests import (
    BoardCreateRequest,
    BoardUpdateRequest,
    WorkItemAssignRequest,
    WorkItemCommentRequest,
    WorkItemCommentsList,
    WorkItemCompleteRequest,
    WorkItemCreateRequest,
    WorkItemMoveRequest,
    WorkItemUpdateRequest,
    WorkQueueCreateRequest,
    WorkQueueMemberAddRequest,
    WorkQueueMemberRemoveRequest,
    WorkQueueMembersList,
    WorkQueueUpdateRequest,
)
from core.worktracker.service import WorkItemMineSummary


class WorkItemsListPayload(WorktrackerModel):
    board_id: str | None = None
    namespace: str | None = None
    kind: WorkItemKind | None = None
    state: WorkItemState | None = None
    work_queue_id: str | None = None
    assignee_user_id: str | None = None
    assignee_flow_id: str | None = None
    exclude_terminal: bool = False
    queue_unclaimed_only: bool = False
    work_queue_ids: list[str] | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class WorkItemsMineSummaryPayload(StrictBaseModel):
    pass


class WorkItemIdPayload(StrictBaseModel):
    work_item_id: str = Field(min_length=1)


class WorkItemUpdatePayload(WorkItemUpdateRequest):
    work_item_id: str = Field(min_length=1)


class WorkItemAssignPayload(WorkItemAssignRequest):
    work_item_id: str = Field(min_length=1)


class WorkItemMovePayload(WorkItemMoveRequest):
    work_item_id: str = Field(min_length=1)


class WorkItemCommentPayload(WorkItemCommentRequest):
    work_item_id: str = Field(min_length=1)


class WorkItemCompletePayload(WorkItemCompleteRequest):
    work_item_id: str = Field(min_length=1)


class BoardsListPayload(StrictBaseModel):
    namespace: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BoardIdPayload(StrictBaseModel):
    board_id: str = Field(min_length=1)


class BoardUpdatePayload(BoardUpdateRequest):
    board_id: str = Field(min_length=1)


class WorkQueuesListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class WorkQueueIdPayload(StrictBaseModel):
    work_queue_id: str = Field(min_length=1)


class WorkQueueUpdatePayload(WorkQueueUpdateRequest):
    work_queue_id: str = Field(min_length=1)


class WorkQueueMemberAddPayload(WorkQueueMemberAddRequest):
    work_queue_id: str = Field(min_length=1)


class WorkQueueMemberRemovePayload(WorkQueueMemberRemoveRequest):
    work_queue_id: str = Field(min_length=1)


def _company_id() -> str:
    return require_active_company().company_id


def _actor(user: User) -> UserActor:
    return UserActor(user_id=user.user_id)






async def _with_policy(
    di: Di,
    item: WorkItem,
    user: User,
) -> WorkItem:
    authorized = await di.work_item_service.operator_authorized(item, user.user_id)
    policy = build_interaction_policy(item, operator_authorized=authorized)
    return item.model_copy(update={"interaction_policy": policy})


async def op_work_items_list(
    payload: WorkItemsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[WorkItem]:
    _ = user, di
    company_id = _company_id()
    items = await WorkItem.list_work_items(
        company_id,
        board_id=payload.board_id,
        namespace=payload.namespace,
        kind=payload.kind,
        state=payload.state,
        work_queue_id=payload.work_queue_id,
        assignee_user_id=payload.assignee_user_id,
        assignee_flow_id=payload.assignee_flow_id,
        exclude_terminal=payload.exclude_terminal,
        queue_unclaimed_only=payload.queue_unclaimed_only,
        work_queue_ids=payload.work_queue_ids,
        limit=payload.limit,
        offset=payload.offset,
    )
    total = await WorkItem.count_work_items(
        company_id,
        board_id=payload.board_id,
        namespace=payload.namespace,
        kind=payload.kind,
        state=payload.state,
        work_queue_id=payload.work_queue_id,
        assignee_user_id=payload.assignee_user_id,
        assignee_flow_id=payload.assignee_flow_id,
        exclude_terminal=payload.exclude_terminal,
        queue_unclaimed_only=payload.queue_unclaimed_only,
        work_queue_ids=payload.work_queue_ids,
    )
    return OffsetPage[WorkItem](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_work_items_mine_summary(
    payload: WorkItemsMineSummaryPayload,
    *,
    user: User,
    di: Di,
) -> WorkItemMineSummary:
    _ = payload
    return await di.work_item_service.mine_summary(_company_id(), user.user_id)


async def op_work_items_get(
    payload: WorkItemIdPayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    try:
        item = await WorkItem.require_in_company(_company_id(), payload.work_item_id)
    except ValueError as exc:
        raise_not_found(exc)
    return await _with_policy(di, item, user)


async def op_work_items_create(
    payload: WorkItemCreateRequest,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    actor = _actor(user)
    if payload.assignment is not None:
        return await di.work_item_service.create(
            company_id=_company_id(),
            title=payload.title,
            created_by=actor,
            description=payload.description,
            kind=payload.kind,
            namespace=payload.namespace,
            board_id=payload.board_id,
            board_column_id=payload.board_column_id,
            priority=payload.priority,
            due_date=payload.due_date,
            labels=payload.labels,
            assignment=payload.assignment,
            blocking=payload.blocking,
            links=payload.links,
            variables=payload.variables,
            attachments=payload.attachments,
        )
    return await di.work_item_service.create_manual_task(
        company_id=_company_id(),
        title=payload.title,
        created_by=actor,
        description=payload.description,
        kind=payload.kind,
        namespace=payload.namespace,
        board_id=payload.board_id,
        board_column_id=payload.board_column_id,
        priority=payload.priority,
        due_date=payload.due_date,
        labels=payload.labels,
        blocking=payload.blocking,
        links=payload.links,
        variables=payload.variables,
        attachments=payload.attachments,
    )


async def op_work_items_update(
    payload: WorkItemUpdatePayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    _ = user
    try:
        return await di.work_item_service.update(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            due_date=payload.due_date,
            labels=payload.labels,
            links=payload.links,
            variables=payload.variables,
            attachments=payload.attachments,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_work_items_assign(
    payload: WorkItemAssignPayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    _ = user
    try:
        return await di.work_item_service.reassign(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            assignment=payload.assignment,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_work_items_move(
    payload: WorkItemMovePayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    _ = user
    try:
        return await di.work_item_service.move(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            board_column_id=payload.board_column_id,
            state=payload.state,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_work_items_claim(
    payload: WorkItemIdPayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    try:
        item = await di.work_item_service.claim(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            user_id=user.user_id,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return await _with_policy(di, item, user)


async def op_work_items_comment(
    payload: WorkItemCommentPayload,
    *,
    user: User,
    di: Di,
) -> WorkItemComment:
    try:
        return await di.work_item_service.add_comment(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            author=_actor(user),
            role=WorkItemCommentRole.OPERATOR,
            text=payload.text,
            files=payload.files,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_work_items_comments_list(
    payload: WorkItemIdPayload,
    *,
    user: User,
    di: Di,
) -> WorkItemCommentsList:
    _ = user, di
    items = await WorkItemComment.list_comments(_company_id(), payload.work_item_id)
    return WorkItemCommentsList(items=items)


async def op_work_items_complete(
    payload: WorkItemCompletePayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    resolution = WorkItemResolution(
        text=payload.resolution_text,
        files=payload.resolution_files,
        resolved_by=_actor(user),
    )
    try:
        completion = await di.work_item_service.complete(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
            resolution=resolution,
            terminal_state=payload.terminal_state,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return await _with_policy(di, completion.work_item, user)


async def op_work_items_cancel(
    payload: WorkItemIdPayload,
    *,
    user: User,
    di: Di,
) -> WorkItem:
    try:
        completion = await di.work_item_service.cancel(
            company_id=_company_id(),
            work_item_id=payload.work_item_id,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return await _with_policy(di, completion.work_item, user)


async def op_boards_list(
    payload: BoardsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[Board]:
    _ = user
    items = await di.work_item_service.list_boards(
        _company_id(), namespace=payload.namespace
    )
    total = len(items)
    page_items = items[payload.offset : payload.offset + payload.limit]
    return OffsetPage[Board](
        items=page_items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_boards_get(
    payload: BoardIdPayload,
    *,
    user: User,
    di: Di,
) -> Board:
    _ = user, di
    try:
        return await Board.get_board(_company_id(), payload.board_id)
    except ValueError as exc:
        raise_not_found(exc)


async def op_boards_create(
    payload: BoardCreateRequest,
    *,
    user: User,
    di: Di,
) -> Board:
    _ = user
    return await di.work_item_service.create_board(
        company_id=_company_id(),
        name=payload.name,
        columns=payload.columns,
        namespace=payload.namespace,
        board_key=payload.board_key,
    )


async def op_boards_update(
    payload: BoardUpdatePayload,
    *,
    user: User,
    di: Di,
) -> Board:
    _ = user
    try:
        return await di.work_item_service.update_board(
            company_id=_company_id(),
            board_id=payload.board_id,
            name=payload.name,
            columns=payload.columns,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_work_queues_list(
    payload: WorkQueuesListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[WorkQueue]:
    items = await di.work_item_service.list_queues(
        _company_id(), user_id=user.user_id
    )
    total = len(items)
    page_items = items[payload.offset : payload.offset + payload.limit]
    return OffsetPage[WorkQueue](
        items=page_items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_work_queues_create(
    payload: WorkQueueCreateRequest,
    *,
    user: User,
    di: Di,
) -> WorkQueue:
    try:
        return await di.work_item_service.create_queue(
            company_id=_company_id(),
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            creator=_actor(user),
        )
    except ValueError as exc:
        raise_conflict(exc)


async def op_work_queues_update(
    payload: WorkQueueUpdatePayload,
    *,
    user: User,
    di: Di,
) -> WorkQueue:
    try:
        return await di.work_item_service.update_queue(
            company_id=_company_id(),
            work_queue_id=payload.work_queue_id,
            name=payload.name,
            description=payload.description,
            actor_user_id=user.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_not_found(exc)


async def op_work_queues_delete(
    payload: WorkQueueIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    try:
        await di.work_item_service.delete_queue(
            company_id=_company_id(),
            work_queue_id=payload.work_queue_id,
            actor_user_id=user.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_not_found(exc)


async def op_work_queues_members_list(
    payload: WorkQueueIdPayload,
    *,
    user: User,
    di: Di,
) -> WorkQueueMembersList:
    try:
        await di.authz_service.require_can_view(
            AuthzObject.work_queue(payload.work_queue_id), user_id=user.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    items = await di.work_item_service.list_queue_members(payload.work_queue_id)
    return WorkQueueMembersList(items=items)


async def op_work_queues_member_add(
    payload: WorkQueueMemberAddPayload,
    *,
    user: User,
    di: Di,
) -> WorkQueueMember:
    try:
        return await di.work_item_service.add_queue_member(
            company_id=_company_id(),
            work_queue_id=payload.work_queue_id,
            member=payload.member,
            role=payload.role,
            actor_user_id=user.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_work_queues_member_remove(
    payload: WorkQueueMemberRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    try:
        removed = await di.work_item_service.remove_queue_member(
            work_queue_id=payload.work_queue_id,
            member=payload.member,
            actor_user_id=user.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    if not removed:
        raise WsCommandError("not_found", "Queue member not found", error_code='not_found')
