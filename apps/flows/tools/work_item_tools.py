"""
Тулы работы с задачами WorkItem для агентов.

Агент может создать задачу себе, другому агенту, оператору (в очередь) или
человеку; завершить задачу; получить список своих/командных задач.
Fire-and-forget: задача с `blocking=false` создаётся и не ждёт ответа.
"""

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.services.platform_facades import get_work_item_service
from apps.flows.src.tools.decorator import tool
from core.context import require_active_company
from core.files.file_ref import FileRef
from core.types import JsonObject
from core.variables.models import normalize_variables_map
from core.worktracker.models import (
    AgentActor,
    AgentAssignment,
    QueueAssignment,
    UnassignedAssignment,
    UsersAssignment,
    WorkActor,
    WorkItemAssignment,
    WorkItemKind,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
)

if TYPE_CHECKING:
    from core.state import ExecutionState


class WorkItemCreateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, description="Краткий заголовок задачи.")
    description: str = Field(default="", description="Подробное описание задачи.")
    assignee_type: str = Field(
        default="unassigned",
        description="Кому: unassigned | self | agent | user | queue.",
    )
    assignee_flow_id: str | None = Field(default=None, description="flow_id агента (assignee_type=agent).")
    assignee_user_id: str | None = Field(default=None, description="user_id человека (assignee_type=user).")
    assignee_queue_slug: str | None = Field(default=None, description="slug очереди (assignee_type=queue).")
    priority: str = Field(default="normal", description="low | normal | high | urgent.")
    blocking: bool = Field(default=False, description="true — задача блокирует (HITL); false — fire-and-forget.")


class WorkItemCompleteArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    work_item_id: str = Field(..., min_length=1)
    resolution_text: str = Field(default="", description="Итог/результат задачи.")
    resolution_files: list[FileRef] = Field(
        default_factory=list,
        description="Вложения к итогу (FileRef). По умолчанию state.files.",
    )


class WorkItemListArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state_filter: str | None = Field(
        default=None,
        description="Фильтр по состоянию: open|in_progress|blocked|done|cancelled|failed.",
    )


async def _build_assignment(args: WorkItemCreateArgs, state: "ExecutionState") -> WorkItemAssignment:
    company_id = require_active_company().company_id
    if args.assignee_type == "self":
        return AgentAssignment(flow_id=state.session_flow_id)
    if args.assignee_type == "agent":
        if not args.assignee_flow_id:
            raise ValueError("assignee_type=agent требует assignee_flow_id")
        return AgentAssignment(flow_id=args.assignee_flow_id)
    if args.assignee_type == "user":
        if not args.assignee_user_id:
            raise ValueError("assignee_type=user требует assignee_user_id")
        return UsersAssignment(user_ids=[args.assignee_user_id])
    if args.assignee_type == "queue":
        if not args.assignee_queue_slug:
            raise ValueError("assignee_type=queue требует assignee_queue_slug")
        queue = await get_work_item_service().get_queue_by_slug(company_id, args.assignee_queue_slug)
        return QueueAssignment(work_queue_id=queue.work_queue_id)
    return UnassignedAssignment()


@tool(
    name="work_item_create",
    description="Создаёт задачу WorkItem (себе, другому агенту, оператору в очередь или человеку). По умолчанию fire-and-forget (не ждёт ответа).",
    tags=["misc", "worktracker"],
    parameters_model=WorkItemCreateArgs,
)
async def work_item_create(
    title: str,
    description: str = "",
    assignee_type: str = "unassigned",
    assignee_flow_id: str | None = None,
    assignee_user_id: str | None = None,
    assignee_queue_slug: str | None = None,
    priority: str = "normal",
    blocking: bool = False,
    *,
    state: "ExecutionState",
) -> JsonObject:
    args = WorkItemCreateArgs(
        title=title,
        description=description,
        assignee_type=assignee_type,
        assignee_flow_id=assignee_flow_id,
        assignee_user_id=assignee_user_id,
        assignee_queue_slug=assignee_queue_slug,
        priority=priority,
        blocking=blocking,
    )
    company_id = require_active_company().company_id
    assignment = await _build_assignment(args, state)
    created_by: WorkActor = AgentActor(flow_id=state.session_flow_id, session_id=state.session_id)
    kind = WorkItemKind.AGENT_JOB if args.assignee_type in ("self", "agent") else WorkItemKind.GENERIC
    work_item = await get_work_item_service().create(
        company_id=company_id,
        title=args.title,
        created_by=created_by,
        description=args.description,
        kind=kind,
        priority=WorkItemPriority(args.priority),
        assignment=assignment,
        blocking=args.blocking,
        variables=normalize_variables_map(state.variables),
        attachments=list(state.files),
    )
    return {"work_item_id": work_item.work_item_id, "state": work_item.state.value}


@tool(
    name="work_item_complete",
    description="Завершает задачу WorkItem с итоговым результатом.",
    tags=["misc", "worktracker"],
    parameters_model=WorkItemCompleteArgs,
)
async def work_item_complete(
    work_item_id: str,
    resolution_text: str = "",
    resolution_files: list[FileRef] | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    company_id = require_active_company().company_id
    resolved_files = resolution_files if resolution_files is not None else list(state.files)
    completion = await get_work_item_service().complete(
        company_id=company_id,
        work_item_id=work_item_id,
        resolution=WorkItemResolution(text=resolution_text, files=resolved_files),
    )
    return {"work_item_id": completion.work_item.work_item_id, "state": completion.work_item.state.value}


@tool(
    name="work_item_list",
    description="Возвращает список задач WorkItem компании (опционально по состоянию).",
    tags=["misc", "worktracker"],
    parameters_model=WorkItemListArgs,
)
async def work_item_list(
    state_filter: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    company_id = require_active_company().company_id
    parsed_state = WorkItemState(state_filter) if state_filter else None
    items = await get_work_item_service().list(company_id, state=parsed_state, limit=50)
    return {
        "items": [
            {
                "work_item_id": item.work_item_id,
                "title": item.title,
                "state": item.state.value,
                "kind": item.kind.value,
            }
            for item in items
        ]
    }
