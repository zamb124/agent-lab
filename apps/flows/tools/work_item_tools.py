"""Builtin tools WorkItem для flow-employee и Lara (зеркало WorkItemService / REST)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from apps.flows.src.clients.worktracker_client import WorktrackerClient
from apps.flows.src.tools.decorator import tool
from core.context import require_active_company, require_context
from core.files.file_ref import FileRef
from core.identity.flow_employee import flow_employee_user_id
from core.models import StrictBaseModel
from core.types import JsonObject
from core.worktracker.models import (
    QueueAssignment,
    UnassignedAssignment,
    UserActor,
    UsersAssignment,
    WorkItem,
    WorkItemAssignment,
    WorkItemCommentRole,
    WorkItemKind,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
)

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["worktracker"]

AssigneeType = Literal["unassigned", "self", "user", "queue", "flow_employee", "agent"]
TerminalCompleteState = Literal["done", "failed"]
PriorityLiteral = Literal["low", "normal", "high", "urgent"]
KindLiteral = Literal["generic", "agent_job", "operator_handoff", "crm_activity"]


def _assignment_summary(assignment: WorkItemAssignment) -> JsonObject:
    return assignment.model_dump(mode="json")


def _work_item_brief(item: WorkItem) -> JsonObject:
    description = item.description
    preview = description if len(description) <= 240 else f"{description[:237]}..."
    return {
        "work_item_id": item.work_item_id,
        "title": item.title,
        "description_preview": preview,
        "state": item.state.value,
        "kind": item.kind.value,
        "priority": item.priority.value,
        "due_date": item.due_date.isoformat() if item.due_date is not None else None,
        "labels": list(item.labels),
        "board_id": item.board_id,
        "board_column_id": item.board_column_id,
        "namespace": item.namespace,
        "blocking": item.blocking,
        "assignment": _assignment_summary(item.assignment),
    }


def _work_item_detail(item: WorkItem) -> JsonObject:
    brief = _work_item_brief(item)
    brief["description"] = item.description
    brief["links"] = [link.model_dump(mode="json") for link in item.links]
    brief["variables"] = {
        key: entry.model_dump(mode="json") for key, entry in item.variables.items()
    }
    brief["attachments"] = [ref.model_dump(mode="json") for ref in item.attachments]
    brief["resolution"] = (
        item.resolution.model_dump(mode="json") if item.resolution is not None else None
    )
    brief["created_at"] = item.created_at.isoformat()
    brief["updated_at"] = item.updated_at.isoformat()
    return brief


def _parse_optional_due_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        raise ValueError("due_date: пустая строка запрещена; передай ISO 8601 или omit/null")
    return datetime.fromisoformat(stripped.replace("Z", "+00:00"))


class WorkItemCreateArgs(StrictBaseModel):
    title: str = Field(
        ...,
        min_length=1,
        description="Краткий заголовок WorkItem. Не выдумывай work_item_id.",
    )
    description: str = Field(
        default="",
        description="Markdown-описание задачи. По умолчанию пустая строка.",
    )
    assignee_type: AssigneeType = Field(
        default="unassigned",
        description=(
            "Кому назначить: unassigned | self (flow_employee текущего session flow) | "
            "user (нужен assignee_user_id из team_resolve_user/team_list_members) | "
            "queue (нужен assignee_queue_slug) | flow_employee (нужен assignee_flow_id). "
            "Синоним agent = flow_employee (совместимость со старыми вызовами)."
        ),
    )
    assignee_flow_id: str | None = Field(
        default=None,
        description="flow_id сотрудника-flow при assignee_type=flow_employee|agent. Не выдумывай.",
    )
    assignee_user_id: str | None = Field(
        default=None,
        description=(
            "user_id человека или flow_employee_* при assignee_type=user. "
            "Бери только из team_list_members / team_resolve_user / UI context."
        ),
    )
    assignee_queue_slug: str | None = Field(
        default=None,
        description="work_queue_slug при assignee_type=queue. Сначала work_queue_list / get_by_slug.",
    )
    priority: PriorityLiteral = Field(
        default="normal",
        description="Приоритет: low | normal | high | urgent.",
    )
    blocking: bool = Field(
        default=False,
        description="true — блокирующая; false — fire-and-forget. По умолчанию false.",
    )
    kind: KindLiteral | None = Field(
        default=None,
        description=(
            "WorkItemKind. Omit — auto: agent_job для self/flow_employee, иначе generic. "
            "operator_handoff обычно создаёт hitl_operator_task, не этот тул."
        ),
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace пространства. Omit/null — без namespace; не подставляй default сам.",
    )
    board_id: str | None = Field(
        default=None,
        description="board_id. Omit — ensure_generic_board (как UI create_manual_task).",
    )
    board_column_id: str | None = Field(
        default=None,
        description="Колонка доски. Omit — placement сервиса.",
    )
    due_date: str | None = Field(
        default=None,
        description="Дедлайн ISO 8601. Omit/null — без due.",
    )
    labels: list[str] = Field(default_factory=list, description="Метки. По умолчанию [].")
    attachment_file_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Явный список file_id вложений. Не копирует state.files молча — передай ids осознанно."
        ),
    )


class WorkItemCompleteArgs(StrictBaseModel):
    work_item_id: str = Field(
        ...,
        min_length=1,
        description="work_item_id из list_mine/list/get/create. Не выводи из title.",
    )
    resolution_text: str = Field(
        default="",
        description="Текст итога (resolution). По умолчанию пустая строка.",
    )
    terminal_state: TerminalCompleteState = Field(
        default="done",
        description="Терминал: done | failed. Для отмены — work_item_cancel.",
    )
    resolution_file_ids: list[str] = Field(
        default_factory=list,
        description="file_id вложений к итогу. Пустой — без файлов (не берёт state.files молча).",
    )


class WorkItemListArgs(StrictBaseModel):
    state_filter: str | None = Field(
        default=None,
        description="Фильтр state: open|in_progress|blocked|done|cancelled|failed. Omit — любой.",
    )
    kind: str | None = Field(
        default=None,
        description="Фильтр kind: generic|agent_job|operator_handoff|crm_activity.",
    )
    board_id: str | None = Field(default=None, description="Фильтр по board_id.")
    namespace: str | None = Field(default=None, description="Фильтр по namespace.")
    work_queue_id: str | None = Field(default=None, description="Одна очередь (work_queue_id).")
    work_queue_ids: list[str] | None = Field(
        default=None,
        description="Несколько очередей. Для inbox unclaimed — с queue_unclaimed_only.",
    )
    assignee_user_id: str | None = Field(
        default=None,
        description=(
            "Фильтр assignee. Для «мои задачи» НЕ используй этот тул — зови work_item_list_mine."
        ),
    )
    assignee_flow_id: str | None = Field(
        default=None,
        description="Фильтр по flow_id исполнителя-employee.",
    )
    exclude_terminal: bool = Field(
        default=False,
        description="true — скрыть done|cancelled|failed.",
    )
    queue_unclaimed_only: bool = Field(
        default=False,
        description="true — только unclaimed queue items (нужны work_queue_ids).",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Максимум записей (1–200).")
    offset: int = Field(default=0, ge=0, description="Смещение пагинации.")


class WorkItemListMineArgs(StrictBaseModel):
    include_terminal: bool = Field(
        default=False,
        description="false (default) — только non-terminal; true — включая терминальные.",
    )
    state_filter: str | None = Field(
        default=None,
        description="Опциональный фильтр одного state поверх mine-scope.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Максимум записей (1–200).")
    offset: int = Field(default=0, ge=0, description="Смещение пагинации.")


class WorkItemGetArgs(StrictBaseModel):
    work_item_id: str = Field(
        ...,
        min_length=1,
        description="work_item_id из list_mine/list/create/context. Не выдумывай.",
    )


class WorkItemUpdateArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1, description="work_item_id для PATCH полей.")
    title: str | None = Field(default=None, description="Новый заголовок. Omit — не менять.")
    description: str | None = Field(default=None, description="Новое описание. Omit — не менять.")
    priority: PriorityLiteral | None = Field(
        default=None,
        description="Новый приоритет. Omit — не менять.",
    )
    due_date: str | None = Field(
        default=None,
        description="ISO 8601 due_date. Omit — не менять.",
    )
    labels: list[str] | None = Field(
        default=None,
        description="Полная замена labels. Omit — не менять.",
    )


class WorkItemAssignArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1, description="work_item_id non-terminal задачи.")
    assignee_type: AssigneeType = Field(
        ...,
        description=(
            "unassigned | self | user | queue | flow_employee (agent — синоним flow_employee). "
            "Перед user — team_resolve_user; перед queue — work_queue_get_by_slug."
        ),
    )
    assignee_flow_id: str | None = Field(default=None, description="Для flow_employee|agent.")
    assignee_user_id: str | None = Field(
        default=None,
        description="Для user — opaque user_id из team tools.",
    )
    assignee_queue_slug: str | None = Field(default=None, description="Для queue — slug.")


class WorkItemMoveArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1, description="work_item_id для move.")
    board_column_id: str | None = Field(
        default=None,
        description="Колонка доски (из work_board_get). Меняет state колонки.",
    )
    item_state: str | None = Field(
        default=None,
        description="Явный WorkItemState без колонки: open|in_progress|blocked.",
    )


class WorkItemClaimArgs(StrictBaseModel):
    work_item_id: str = Field(
        ...,
        min_length=1,
        description="Queue-assigned work_item_id. Текущий user должен быть member очереди.",
    )


class WorkItemCancelArgs(StrictBaseModel):
    work_item_id: str = Field(
        ...,
        min_length=1,
        description="work_item_id для cancel (terminal cancelled).",
    )


class WorkItemCommentAddArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1, description="work_item_id activity thread.")
    text: str = Field(
        ...,
        min_length=1,
        description=(
            "Текст внутренней заметки команды (WorkItemComment). "
            "Не HITL-диалог с внешним пользователем."
        ),
    )


class WorkItemCommentsListArgs(StrictBaseModel):
    work_item_id: str = Field(..., min_length=1, description="work_item_id для list comments.")


class WorkItemMineSummaryArgs(StrictBaseModel):
    """Без аргументов — summary для текущего JWT user."""


async def _build_assignment(
    *,
    assignee_type: str,
    assignee_flow_id: str | None,
    assignee_user_id: str | None,
    assignee_queue_slug: str | None,
    state: "ExecutionState",
) -> WorkItemAssignment:
    company_id = require_active_company().company_id
    normalized = "flow_employee" if assignee_type == "agent" else assignee_type
    if normalized == "self":
        return UsersAssignment(user_ids=[flow_employee_user_id(state.session_flow_id)])
    if normalized == "flow_employee":
        if not assignee_flow_id:
            raise ValueError("assignee_type=flow_employee|agent требует assignee_flow_id")
        return UsersAssignment(user_ids=[flow_employee_user_id(assignee_flow_id)])
    if normalized == "user":
        if not assignee_user_id:
            raise ValueError("assignee_type=user требует assignee_user_id из team tools")
        return UsersAssignment(user_ids=[assignee_user_id])
    if normalized == "queue":
        if not assignee_queue_slug:
            raise ValueError("assignee_type=queue требует assignee_queue_slug")
        queue = await WorktrackerClient().get_queue_by_slug(company_id, assignee_queue_slug)
        return QueueAssignment(work_queue_id=queue.work_queue_id)
    if normalized == "unassigned":
        return UnassignedAssignment()
    raise ValueError(
        f"Неизвестный assignee_type={assignee_type!r}; "
        + "ожидается unassigned|self|user|queue|flow_employee|agent"
    )


def _file_refs_from_ids(file_ids: list[str], state: "ExecutionState") -> list[FileRef]:
    if not file_ids:
        return []
    by_id = {ref.file_id: ref for ref in state.files}
    resolved: list[FileRef] = []
    for file_id in file_ids:
        ref = by_id.get(file_id)
        if ref is None:
            raise ValueError(
                f"file_id={file_id!r} нет в state.files; сначала create_file / прикрепи файл к run"
            )
        resolved.append(ref)
    return resolved


@tool(
    name="work_item_create",
    description=(
        "Creates a WorkItem on the generic board (UI create_manual_task semantics). "
        "Use for new work for self, a person (user_id from team tools), a queue slug, "
        "or another flow employee. Default assignee_type=unassigned places the card on the board "
        "without assignee. Do not invent work_item_id. Returns work_item_id, state, board_id."
    ),
    tags=_TAGS,
    parameters_model=WorkItemCreateArgs,
)
async def work_item_create(
    title: str,
    description: str = "",
    assignee_type: AssigneeType = "unassigned",
    assignee_flow_id: str | None = None,
    assignee_user_id: str | None = None,
    assignee_queue_slug: str | None = None,
    priority: PriorityLiteral = "normal",
    blocking: bool = False,
    kind: KindLiteral | None = None,
    namespace: str | None = None,
    board_id: str | None = None,
    board_column_id: str | None = None,
    due_date: str | None = None,
    labels: list[str] | None = None,
    attachment_file_ids: list[str] | None = None,
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
        kind=kind,
        namespace=namespace,
        board_id=board_id,
        board_column_id=board_column_id,
        due_date=due_date,
        labels=labels if labels is not None else [],
        attachment_file_ids=attachment_file_ids if attachment_file_ids is not None else [],
    )
    company_id = require_active_company().company_id
    assignment = await _build_assignment(
        assignee_type=args.assignee_type,
        assignee_flow_id=args.assignee_flow_id,
        assignee_user_id=args.assignee_user_id,
        assignee_queue_slug=args.assignee_queue_slug,
        state=state,
    )
    created_by = UserActor(user_id=require_context().user.user_id)
    normalized_assignee = (
        "flow_employee" if args.assignee_type == "agent" else args.assignee_type
    )
    if args.kind is not None:
        resolved_kind = WorkItemKind(args.kind)
    elif normalized_assignee in ("self", "flow_employee"):
        resolved_kind = WorkItemKind.AGENT_JOB
    else:
        resolved_kind = WorkItemKind.GENERIC
    attachments = _file_refs_from_ids(args.attachment_file_ids, state)
    work_item = await WorktrackerClient().create_manual_task(
        company_id=company_id,
        title=args.title,
        created_by=created_by,
        description=args.description,
        kind=resolved_kind,
        namespace=args.namespace,
        board_id=args.board_id,
        board_column_id=args.board_column_id,
        priority=WorkItemPriority(args.priority),
        due_date=_parse_optional_due_date(args.due_date),
        labels=list(args.labels),
        assignment=assignment,
        blocking=args.blocking,
        attachments=attachments,
    )
    return {
        "work_item_id": work_item.work_item_id,
        "state": work_item.state.value,
        "board_id": work_item.board_id,
        "board_column_id": work_item.board_column_id,
        "assignment": _assignment_summary(work_item.assignment),
    }


@tool(
    name="work_item_complete",
    description=(
        "Completes a WorkItem with terminal_state done or failed and optional resolution text. "
        "Use after work_item_get when the work is finished. "
        "Do not use for cancel — call work_item_cancel. "
        "Requires exact work_item_id from a prior tool. Returns work_item_id and state."
    ),
    tags=_TAGS,
    parameters_model=WorkItemCompleteArgs,
)
async def work_item_complete(
    work_item_id: str,
    resolution_text: str = "",
    terminal_state: TerminalCompleteState = "done",
    resolution_file_ids: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    args = WorkItemCompleteArgs(
        work_item_id=work_item_id,
        resolution_text=resolution_text,
        terminal_state=terminal_state,
        resolution_file_ids=resolution_file_ids if resolution_file_ids is not None else [],
    )
    company_id = require_active_company().company_id
    files = _file_refs_from_ids(args.resolution_file_ids, state)
    completion = await WorktrackerClient().complete(
        company_id=company_id,
        work_item_id=args.work_item_id,
        resolution=WorkItemResolution(text=args.resolution_text, files=files),
        terminal_state=WorkItemState(args.terminal_state),
    )
    return {
        "work_item_id": completion.work_item.work_item_id,
        "state": completion.work_item.state.value,
        "newly_terminal": completion.newly_terminal,
    }


@tool(
    name="work_item_list",
    description=(
        "Filtered company WorkItem list (board/queue/admin). "
        "Do NOT use for «my tasks» — call work_item_list_mine instead. "
        "Pass explicit filters (state_filter, board_id, work_queue_id(s), assignee_user_id, "
        "exclude_terminal). Returns items[] with brief fields including work_item_id."
    ),
    tags=_TAGS,
    parameters_model=WorkItemListArgs,
)
async def work_item_list(
    state_filter: str | None = None,
    kind: str | None = None,
    board_id: str | None = None,
    namespace: str | None = None,
    work_queue_id: str | None = None,
    work_queue_ids: list[str] | None = None,
    assignee_user_id: str | None = None,
    assignee_flow_id: str | None = None,
    exclude_terminal: bool = False,
    queue_unclaimed_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemListArgs(
        state_filter=state_filter,
        kind=kind,
        board_id=board_id,
        namespace=namespace,
        work_queue_id=work_queue_id,
        work_queue_ids=work_queue_ids,
        assignee_user_id=assignee_user_id,
        assignee_flow_id=assignee_flow_id,
        exclude_terminal=exclude_terminal,
        queue_unclaimed_only=queue_unclaimed_only,
        limit=limit,
        offset=offset,
    )
    company_id = require_active_company().company_id
    parsed_item_state = WorkItemState(args.state_filter) if args.state_filter else None
    parsed_kind = WorkItemKind(args.kind) if args.kind else None
    items = await WorktrackerClient().list(
        company_id,
        board_id=args.board_id,
        namespace=args.namespace,
        kind=parsed_kind,
        state=parsed_item_state,
        work_queue_id=args.work_queue_id,
        assignee_user_id=args.assignee_user_id,
        assignee_flow_id=args.assignee_flow_id,
        exclude_terminal=args.exclude_terminal,
        queue_unclaimed_only=args.queue_unclaimed_only,
        work_queue_ids=args.work_queue_ids,
        limit=args.limit,
        offset=args.offset,
    )
    return {
        "items": [_work_item_brief(item) for item in items],
        "limit": args.limit,
        "offset": args.offset,
    }


@tool(
    name="work_item_list_mine",
    description=(
        "Returns WorkItems assigned to the current actor (JWT user_id — flow employee or human). "
        "First step after assignment wake-up or when asked «what is on me». "
        "Default excludes terminal states. Do not use work_item_list for this. "
        "Returns items[] with work_item_id, title, state, priority, due_date, assignment."
    ),
    tags=_TAGS,
    parameters_model=WorkItemListMineArgs,
)
async def work_item_list_mine(
    include_terminal: bool = False,
    state_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemListMineArgs(
        include_terminal=include_terminal,
        state_filter=state_filter,
        limit=limit,
        offset=offset,
    )
    company_id = require_active_company().company_id
    user_id = require_context().user.user_id
    parsed_item_state = WorkItemState(args.state_filter) if args.state_filter else None
    items = await WorktrackerClient().list(
        company_id,
        assignee_user_id=user_id,
        state=parsed_item_state,
        exclude_terminal=not args.include_terminal,
        limit=args.limit,
        offset=args.offset,
    )
    return {
        "items": [_work_item_brief(item) for item in items],
        "assignee_user_id": user_id,
        "limit": args.limit,
        "offset": args.offset,
    }


@tool(
    name="work_item_get",
    description=(
        "Loads one WorkItem by work_item_id (full detail: description, links, variables, "
        "attachments, resolution). Call before update/complete/comment when list brief is insufficient. "
        "Never invent work_item_id."
    ),
    tags=_TAGS,
    parameters_model=WorkItemGetArgs,
)
async def work_item_get(
    work_item_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemGetArgs(work_item_id=work_item_id)
    item = await WorktrackerClient().get(
        require_active_company().company_id,
        args.work_item_id,
    )
    return _work_item_detail(item)


@tool(
    name="work_item_mine_summary",
    description=(
        "Inbox counters for the current user: assigned_open_count, queue_inbox_count, "
        "and work_queue_ids the user belongs to. Use for badges / deciding whether to list "
        "queue unclaimed items. Does not replace work_item_list_mine."
    ),
    tags=_TAGS,
    parameters_model=WorkItemMineSummaryArgs,
)
async def work_item_mine_summary(*, state: "ExecutionState") -> JsonObject:
    _ = state
    summary = await WorktrackerClient().mine_summary(
        require_active_company().company_id,
        require_context().user.user_id,
    )
    return {
        "assigned_open_count": summary.assigned_open_count,
        "queue_inbox_count": summary.queue_inbox_count,
        "work_queue_ids": list(summary.work_queue_ids),
    }


@tool(
    name="work_item_update",
    description=(
        "Patches WorkItem fields (title, description, priority, due_date, labels). "
        "Omit fields you do not change. Requires work_item_id from get/list. "
        "Returns updated brief."
    ),
    tags=_TAGS,
    parameters_model=WorkItemUpdateArgs,
)
async def work_item_update(
    work_item_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: PriorityLiteral | None = None,
    due_date: str | None = None,
    labels: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemUpdateArgs(
        work_item_id=work_item_id,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        labels=labels,
    )
    due_value = (
        _parse_optional_due_date(args.due_date) if args.due_date is not None else None
    )
    item = await WorktrackerClient().update(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
        title=args.title,
        description=args.description,
        priority=WorkItemPriority(args.priority) if args.priority is not None else None,
        due_date=due_value,
        labels=args.labels,
    )
    return _work_item_brief(item)


@tool(
    name="work_item_assign",
    description=(
        "Reassigns a non-terminal WorkItem (user/queue/self/flow_employee/unassigned). "
        "For people: resolve user_id via team_resolve_user first — never guess ids from names. "
        "Returns updated assignment summary."
    ),
    tags=_TAGS,
    parameters_model=WorkItemAssignArgs,
)
async def work_item_assign(
    work_item_id: str,
    assignee_type: AssigneeType,
    assignee_flow_id: str | None = None,
    assignee_user_id: str | None = None,
    assignee_queue_slug: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    args = WorkItemAssignArgs(
        work_item_id=work_item_id,
        assignee_type=assignee_type,
        assignee_flow_id=assignee_flow_id,
        assignee_user_id=assignee_user_id,
        assignee_queue_slug=assignee_queue_slug,
    )
    assignment = await _build_assignment(
        assignee_type=args.assignee_type,
        assignee_flow_id=args.assignee_flow_id,
        assignee_user_id=args.assignee_user_id,
        assignee_queue_slug=args.assignee_queue_slug,
        state=state,
    )
    item = await WorktrackerClient().reassign(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
        assignment=assignment,
    )
    return {
        "work_item_id": item.work_item_id,
        "assignment": _assignment_summary(item.assignment),
        "state": item.state.value,
    }


@tool(
    name="work_item_move",
    description=(
        "Moves a WorkItem on the board (board_column_id) and/or sets non-terminal item_state. "
        "Get columns from work_board_get. Terminal done/cancelled/failed — use complete/cancel."
    ),
    tags=_TAGS,
    parameters_model=WorkItemMoveArgs,
)
async def work_item_move(
    work_item_id: str,
    board_column_id: str | None = None,
    item_state: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemMoveArgs(
        work_item_id=work_item_id,
        board_column_id=board_column_id,
        item_state=item_state,
    )
    if args.board_column_id is None and args.item_state is None:
        raise ValueError("Нужен board_column_id и/или item_state")
    item = await WorktrackerClient().move(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
        board_column_id=args.board_column_id,
        state=WorkItemState(args.item_state) if args.item_state is not None else None,
    )
    return _work_item_brief(item)


@tool(
    name="work_item_claim",
    description=(
        "Claims a queue-assigned WorkItem for the current user. "
        "Requires membership in the work queue. Use after listing unclaimed inbox items. "
        "Returns updated assignment with claimed_by_user_id."
    ),
    tags=_TAGS,
    parameters_model=WorkItemClaimArgs,
)
async def work_item_claim(
    work_item_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemClaimArgs(work_item_id=work_item_id)
    item = await WorktrackerClient().claim(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
        user_id=require_context().user.user_id,
    )
    return _work_item_brief(item)


@tool(
    name="work_item_cancel",
    description=(
        "Cancels a WorkItem (terminal state=cancelled). "
        "Do not use work_item_complete for cancel. Returns work_item_id and state."
    ),
    tags=_TAGS,
    parameters_model=WorkItemCancelArgs,
)
async def work_item_cancel(
    work_item_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemCancelArgs(work_item_id=work_item_id)
    completion = await WorktrackerClient().cancel(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
    )
    return {
        "work_item_id": completion.work_item.work_item_id,
        "state": completion.work_item.state.value,
        "newly_terminal": completion.newly_terminal,
    }


@tool(
    name="work_item_add_comment",
    description=(
        "Adds an internal activity comment (WorkItemComment) on a WorkItem. "
        "Team-only notes — not the HITL customer conversation. "
        "Author is the current user; role=agent for flow-employee actors."
    ),
    tags=_TAGS,
    parameters_model=WorkItemCommentAddArgs,
)
async def work_item_add_comment(
    work_item_id: str,
    text: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemCommentAddArgs(work_item_id=work_item_id, text=text)
    user_id = require_context().user.user_id
    role = (
        WorkItemCommentRole.AGENT
        if user_id.startswith("flow_employee_")
        else WorkItemCommentRole.USER
    )
    comment = await WorktrackerClient().add_comment(
        company_id=require_active_company().company_id,
        work_item_id=args.work_item_id,
        author=UserActor(user_id=user_id),
        role=role,
        text=args.text,
    )
    return comment.model_dump(mode="json")


@tool(
    name="work_item_list_comments",
    description=(
        "Lists internal activity comments for a WorkItem (not HITL conversation turns). "
        "Returns items[] with comment_id, text, role, author, created_at."
    ),
    tags=_TAGS,
    parameters_model=WorkItemCommentsListArgs,
)
async def work_item_list_comments(
    work_item_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkItemCommentsListArgs(work_item_id=work_item_id)
    comments = await WorktrackerClient().list_comments(
        require_active_company().company_id,
        args.work_item_id,
    )
    return {"items": [c.model_dump(mode="json") for c in comments]}
