"""Worktracker SDK capabilities: HTTP to worktracker REST (same models as the API)."""

from __future__ import annotations

from typing import TypeAlias
from urllib.parse import quote

from pydantic import BaseModel, Field, ValidationError

from apps.worktracker.models.api import (
    BoardCreateRequest,
    BoardUpdateRequest,
    WorkItemAssignRequest,
    WorkItemCommentRequest,
    WorkItemCompleteRequest,
    WorkItemCreateRequest,
    WorkItemMoveRequest,
    WorkItemUpdateRequest,
    WorkQueueCreateRequest,
    WorkQueueMemberAddRequest,
    WorkQueueMemberRemoveRequest,
    WorkQueueUpdateRequest,
)
from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.service_client import ServiceClient, ServiceClientError
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_object
from core.worktracker.models import WorkItemKind, WorkItemState

WorktrackerArgsModel: TypeAlias = type[BaseModel]

_API = "/worktracker/api/v1"

_WORKTRACKER_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "JSON from worktracker REST (product-level fields, no HTTP envelope).",
}


class WorktrackerEmptyArgs(StrictBaseModel):
    """No kwargs."""


class WorktrackerWorkItemIdArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerQueueIdArgs(StrictBaseModel):
    work_queue_id: str = Field(..., min_length=1)


class WorktrackerBoardIdArgs(StrictBaseModel):
    board_id: str = Field(..., min_length=1)


class WorktrackerListArgs(StrictBaseModel):
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
    limit: int = Field(200, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class WorktrackerUpdateArgs(WorkItemUpdateRequest):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerAssignArgs(WorkItemAssignRequest):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerMoveArgs(WorkItemMoveRequest):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerCompleteArgs(WorkItemCompleteRequest):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerCommentArgs(WorkItemCommentRequest):
    work_item_id: str = Field(..., min_length=1)


class WorktrackerQueueUpdateArgs(WorkQueueUpdateRequest):
    work_queue_id: str = Field(..., min_length=1)


class WorktrackerQueueMemberAddArgs(WorkQueueMemberAddRequest):
    work_queue_id: str = Field(..., min_length=1)


class WorktrackerQueueMemberRemoveArgs(WorkQueueMemberRemoveRequest):
    work_queue_id: str = Field(..., min_length=1)


class WorktrackerListBoardsArgs(StrictBaseModel):
    namespace: str | None = None
    limit: int = Field(200, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class WorktrackerBoardUpdateArgs(BoardUpdateRequest):
    board_id: str = Field(..., min_length=1)


def _input_schema(model: WorktrackerArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: WorktrackerArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"worktracker.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_WORKTRACKER_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["worktracker"],
        sdk_namespace="worktracker",
        sdk_method=method,
    )


WORKTRACKER_CAPABILITY_SPECS: tuple[tuple[str, str, str, WorktrackerArgsModel], ...] = (
    (
        "get",
        "Get WorkItem",
        "Returns one WorkItem by work_item_id.",
        WorktrackerWorkItemIdArgs,
    ),
    (
        "list",
        "List WorkItems",
        "Lists WorkItems for the active company with optional filters.",
        WorktrackerListArgs,
    ),
    (
        "mine_summary",
        "WorkItem mine summary",
        "Open assigned count and queue inbox for the current user.",
        WorktrackerEmptyArgs,
    ),
    (
        "create_manual_task",
        "Create WorkItem",
        "Creates a manual WorkItem. company_id and created_by come from execution context.",
        WorkItemCreateRequest,
    ),
    (
        "update",
        "Update WorkItem",
        "Patches title, description, priority, due_date, labels, links, variables, attachments.",
        WorktrackerUpdateArgs,
    ),
    (
        "reassign",
        "Reassign WorkItem",
        "Changes assignment (users / queue / unassigned).",
        WorktrackerAssignArgs,
    ),
    (
        "move",
        "Move WorkItem",
        "Moves a WorkItem to a board column and/or state.",
        WorktrackerMoveArgs,
    ),
    (
        "claim",
        "Claim WorkItem",
        "Claims a queued WorkItem for the current user.",
        WorktrackerWorkItemIdArgs,
    ),
    (
        "complete",
        "Complete WorkItem",
        "Completes a WorkItem with optional resolution.",
        WorktrackerCompleteArgs,
    ),
    (
        "cancel",
        "Cancel WorkItem",
        "Cancels a WorkItem.",
        WorktrackerWorkItemIdArgs,
    ),
    (
        "add_comment",
        "Add WorkItem comment",
        "Adds a comment. Author is the current user.",
        WorktrackerCommentArgs,
    ),
    (
        "list_comments",
        "List WorkItem comments",
        "Lists comments on a WorkItem.",
        WorktrackerWorkItemIdArgs,
    ),
    (
        "list_queues",
        "List work queues",
        "Lists work queues visible to the current user.",
        WorktrackerEmptyArgs,
    ),
    (
        "create_queue",
        "Create work queue",
        "Creates a work queue. Creator is the current user.",
        WorkQueueCreateRequest,
    ),
    (
        "update_queue",
        "Update work queue",
        "Patches queue name/description.",
        WorktrackerQueueUpdateArgs,
    ),
    (
        "list_queue_members",
        "List work queue members",
        "Lists members of a work queue.",
        WorktrackerQueueIdArgs,
    ),
    (
        "add_queue_member",
        "Add work queue member",
        "Adds a member to a work queue.",
        WorktrackerQueueMemberAddArgs,
    ),
    (
        "remove_queue_member",
        "Remove work queue member",
        "Removes a member from a work queue.",
        WorktrackerQueueMemberRemoveArgs,
    ),
    (
        "list_boards",
        "List boards",
        "Lists WorkItem boards, optionally filtered by namespace.",
        WorktrackerListBoardsArgs,
    ),
    (
        "get_board",
        "Get board",
        "Returns one board by board_id.",
        WorktrackerBoardIdArgs,
    ),
    (
        "create_board",
        "Create board",
        "Creates a board with columns.",
        BoardCreateRequest,
    ),
    (
        "update_board",
        "Update board",
        "Patches board name/columns.",
        WorktrackerBoardUpdateArgs,
    ),
)


def worktracker_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"worktracker.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in WORKTRACKER_CAPABILITY_SPECS
    }


def worktracker_args_model_for(method: str) -> WorktrackerArgsModel:
    for spec_method, _title, _description, args_model in WORKTRACKER_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown worktracker capability method: {method}")


WORKTRACKER_CLIENT_METHOD_NAMES: frozenset[str] = frozenset(
    spec[0] for spec in WORKTRACKER_CAPABILITY_SPECS
)


def _seg(value: str) -> str:
    return quote(value, safe="")


def _query_params(args: BaseModel) -> dict[str, str | list[str]]:
    dumped = require_json_object(
        args.model_dump(mode="json", exclude_none=True),
        f"{type(args).__name__}.query",
    )
    params: dict[str, str | list[str]] = {}
    for key, value in dumped.items():
        if isinstance(value, bool):
            params[key] = "true" if value else "false"
            continue
        if isinstance(value, list):
            params[key] = [str(item) for item in value]
            continue
        params[key] = str(value)
    return params


def _body(args: BaseModel, *, exclude: set[str] | None = None) -> JsonObject:
    dumped = args.model_dump(mode="json", exclude=exclude, exclude_none=True)
    return require_json_object(dumped, f"{type(args).__name__}.json")


async def _worktracker_method_call(method: str, args: BaseModel) -> JsonValue:
    http = ServiceClient()
    if method == "get" and isinstance(args, WorktrackerWorkItemIdArgs):
        return await http.get("worktracker", f"{_API}/work-items/{_seg(args.work_item_id)}")
    if method == "list" and isinstance(args, WorktrackerListArgs):
        return await http.get("worktracker", f"{_API}/work-items", params=_query_params(args))
    if method == "mine_summary" and isinstance(args, WorktrackerEmptyArgs):
        return await http.get("worktracker", f"{_API}/work-items/mine/summary")
    if method == "create_manual_task" and isinstance(args, WorkItemCreateRequest):
        return await http.post("worktracker", f"{_API}/work-items", json=_body(args))
    if method == "update" and isinstance(args, WorktrackerUpdateArgs):
        return await http.patch(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}",
            json=_body(args, exclude={"work_item_id"}),
        )
    if method == "reassign" and isinstance(args, WorktrackerAssignArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/assign",
            json=_body(args, exclude={"work_item_id"}),
        )
    if method == "move" and isinstance(args, WorktrackerMoveArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/move",
            json=_body(args, exclude={"work_item_id"}),
        )
    if method == "claim" and isinstance(args, WorktrackerWorkItemIdArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/claim",
        )
    if method == "complete" and isinstance(args, WorktrackerCompleteArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/complete",
            json=_body(args, exclude={"work_item_id"}),
        )
    if method == "cancel" and isinstance(args, WorktrackerWorkItemIdArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/cancel",
        )
    if method == "add_comment" and isinstance(args, WorktrackerCommentArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/comments",
            json=_body(args, exclude={"work_item_id"}),
        )
    if method == "list_comments" and isinstance(args, WorktrackerWorkItemIdArgs):
        return await http.get(
            "worktracker",
            f"{_API}/work-items/{_seg(args.work_item_id)}/comments",
        )
    if method == "list_queues" and isinstance(args, WorktrackerEmptyArgs):
        return await http.get("worktracker", f"{_API}/work-queues")
    if method == "create_queue" and isinstance(args, WorkQueueCreateRequest):
        return await http.post("worktracker", f"{_API}/work-queues", json=_body(args))
    if method == "update_queue" and isinstance(args, WorktrackerQueueUpdateArgs):
        return await http.patch(
            "worktracker",
            f"{_API}/work-queues/{_seg(args.work_queue_id)}",
            json=_body(args, exclude={"work_queue_id"}),
        )
    if method == "list_queue_members" and isinstance(args, WorktrackerQueueIdArgs):
        return await http.get(
            "worktracker",
            f"{_API}/work-queues/{_seg(args.work_queue_id)}/members",
        )
    if method == "add_queue_member" and isinstance(args, WorktrackerQueueMemberAddArgs):
        return await http.post(
            "worktracker",
            f"{_API}/work-queues/{_seg(args.work_queue_id)}/members",
            json=_body(args, exclude={"work_queue_id"}),
        )
    if method == "remove_queue_member" and isinstance(args, WorktrackerQueueMemberRemoveArgs):
        removed = await http.post(
            "worktracker",
            f"{_API}/work-queues/{_seg(args.work_queue_id)}/members/remove",
            json=_body(args, exclude={"work_queue_id"}),
        )
        if removed is None:
            return {"removed": True}
        return removed
    if method == "list_boards" and isinstance(args, WorktrackerListBoardsArgs):
        return await http.get("worktracker", f"{_API}/boards", params=_query_params(args))
    if method == "get_board" and isinstance(args, WorktrackerBoardIdArgs):
        return await http.get("worktracker", f"{_API}/boards/{_seg(args.board_id)}")
    if method == "create_board" and isinstance(args, BoardCreateRequest):
        return await http.post("worktracker", f"{_API}/boards", json=_body(args))
    if method == "update_board" and isinstance(args, WorktrackerBoardUpdateArgs):
        return await http.patch(
            "worktracker",
            f"{_API}/boards/{_seg(args.board_id)}",
            json=_body(args, exclude={"board_id"}),
        )
    raise ValueError(f"Unsupported worktracker capability invoke: {method}")


async def invoke_worktracker_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs and call worktracker REST (Context must be active)."""
    args_model = worktracker_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _worktracker_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
