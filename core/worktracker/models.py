"""
Доменные модели ядра задач WorkItem.

Дискриминированные union строятся по образцу `core/state/interrupt.py`:
поле-дискриминатор `Literal[Enum.MEMBER] = Enum.MEMBER`, обёртка через
`Annotated[..., Field(discriminator=...)]`.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw
from pydantic import ConfigDict, Field, model_validator

from core.files.file_attachments import minimal_file_refs_from_file_ids
from core.files.file_ref import FileRef
from core.identity.flow_employee import flow_employee_user_id
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.types import JsonObject, parse_json_object, require_json_array, require_json_object
from core.variables.models import VariableMap


class WorktrackerModel(StrictBaseModel):
    """Базовая модель ядра задач.

    Отличие от `StrictBaseModel` — `use_enum_values=False`: enum-поля остаются
    членами enum (`WorkItemState`, `WorkItemKind`, ...), а не голыми строками,
    чтобы сохранять типизацию и `.value` в сервисе/репозитории.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=True,
        validate_default=True,
    )


class WorkItemState(StrEnum):
    """Движковое состояние задачи (стейт-машина ядра)."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_WORK_ITEM_STATES: frozenset[WorkItemState] = frozenset(
    {WorkItemState.DONE, WorkItemState.CANCELLED, WorkItemState.FAILED}
)


class WorkItemKind(StrEnum):
    """Происхождение/поведение задачи."""

    GENERIC = "generic"
    OPERATOR_HANDOFF = "operator_handoff"
    AGENT_JOB = "agent_job"
    CRM_ACTIVITY = "crm_activity"


class WorkItemPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# === Actor (кто создал / разрешил) ===


class ActorKind(StrEnum):
    USER = "user"
    SYSTEM = "system"


class UserActor(WorktrackerModel):
    actor_kind: Literal[ActorKind.USER] = ActorKind.USER
    user_id: str = Field(..., min_length=1)


class SystemActor(WorktrackerModel):
    actor_kind: Literal[ActorKind.SYSTEM] = ActorKind.SYSTEM


WorkActor = Annotated[
    UserActor | SystemActor,
    Field(discriminator="actor_kind"),
]


# === Assignment (кому назначена работа) ===


class AssigneeKind(StrEnum):
    UNASSIGNED = "unassigned"
    USERS = "users"
    QUEUE = "queue"


class UnassignedAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.UNASSIGNED] = AssigneeKind.UNASSIGNED


class UsersAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.USERS] = AssigneeKind.USERS
    user_ids: list[str] = Field(..., min_length=1)


class QueueAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.QUEUE] = AssigneeKind.QUEUE
    work_queue_id: str = Field(..., min_length=1)
    claimed_by_user_id: str | None = None


WorkItemAssignment = Annotated[
    UnassignedAssignment | UsersAssignment | QueueAssignment,
    Field(discriminator="assignee_kind"),
]


# === Links (привязки к доменным сущностям платформы) ===


class WorkItemLinkKind(StrEnum):
    CRM_ENTITY = "crm_entity"
    FLOW_SESSION = "flow_session"
    SYNC_MESSAGE = "sync_message"
    RAG_DOCUMENT = "rag_document"
    FILE = "file"
    CALENDAR_EVENT = "calendar_event"
    STOCK_TRANSFER = "stock_transfer"
    STOCK_LOCATION = "stock_location"
    WORK_ITEM = "work_item"


class WorkItemLinkRelation(StrEnum):
    BLOCKS = "blocks"
    RELATED = "related"
    PARENT = "parent"


class CrmEntityLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.CRM_ENTITY] = WorkItemLinkKind.CRM_ENTITY
    entity_id: str = Field(..., min_length=1)


class FlowSessionLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.FLOW_SESSION] = WorkItemLinkKind.FLOW_SESSION
    session_id: str = Field(..., min_length=1)
    a2a_task_id: str | None = None
    context_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None


class SyncMessageLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.SYNC_MESSAGE] = WorkItemLinkKind.SYNC_MESSAGE
    channel_id: str = Field(..., min_length=1)
    message_id: str | None = None


class RagDocumentLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.RAG_DOCUMENT] = WorkItemLinkKind.RAG_DOCUMENT
    document_id: str = Field(..., min_length=1)


class FileLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.FILE] = WorkItemLinkKind.FILE
    file_id: str = Field(..., min_length=1)


class CalendarEventLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.CALENDAR_EVENT] = WorkItemLinkKind.CALENDAR_EVENT
    event_id: str = Field(..., min_length=1)


class StockTransferLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.STOCK_TRANSFER] = WorkItemLinkKind.STOCK_TRANSFER
    transfer_id: str = Field(..., min_length=1)


class StockLocationLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.STOCK_LOCATION] = WorkItemLinkKind.STOCK_LOCATION
    location_id: str = Field(..., min_length=1)


class WorkItemToWorkItemLink(WorktrackerModel):
    link_kind: Literal[WorkItemLinkKind.WORK_ITEM] = WorkItemLinkKind.WORK_ITEM
    work_item_id: str = Field(..., min_length=1)
    relation: WorkItemLinkRelation = WorkItemLinkRelation.RELATED


WorkItemLink = Annotated[
    CrmEntityLink
    | FlowSessionLink
    | SyncMessageLink
    | RagDocumentLink
    | FileLink
    | CalendarEventLink
    | StockTransferLink
    | StockLocationLink
    | WorkItemToWorkItemLink,
    Field(discriminator="link_kind"),
]


# === Хуки жизненного цикла ===


class WorkItemHookEvent(StrEnum):
    """Событие жизненного цикла WorkItem, на которое подписан хук."""

    ASSIGNED = "assigned"
    COMMENT = "comment"
    COMPLETED = "completed"


class WorkItemHook(WorktrackerModel):
    """Binding жизненного цикла для durable-потребителей шины.

    `service`/`path` — метаданные потребителя (flows: path=`platform:events`);
    `binding` — непрозрачные данные (например HITL resume snapshot). HTTP
    dispatch удалён: обработка только через consumer group на `platform:events`.
    """

    event: WorkItemHookEvent
    service: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    binding: JsonObject = Field(default_factory=dict)


class WorkItemResolution(WorktrackerModel):
    text: str = ""
    files: list[FileRef] = Field(default_factory=list)
    resolved_by: WorkActor | None = None

    @model_validator(mode="before")
    @classmethod
    def _stored_file_ids(cls, value: object) -> object:
        def has_legacy_file_ids(raw: object) -> bool:
            if not isinstance(raw, dict):
                return False
            return "file_ids" in raw and "files" not in raw

        if not has_legacy_file_ids(value):
            return value
        stored = require_json_object(value, "resolution")
        file_ids = require_json_array(stored["file_ids"], "resolution.file_ids")
        ids: list[str] = []
        for item in file_ids:
            if not isinstance(item, str):
                raise ValueError("resolution.file_ids must be strings")
            ids.append(item)
        refs = minimal_file_refs_from_file_ids(ids)
        del stored["file_ids"]
        stored["files"] = [
            require_json_object(ref.model_dump(mode="json"), "resolution.files")
            for ref in refs
        ]
        return stored


# === Интерактивный контракт задачи (operator_handoff) ===


class WorkItemInteractionMode(StrEnum):
    """Как оператор взаимодействует с задачей в её карточке."""

    NONE = "none"
    SINGLE_REPLY = "single_reply"
    TAKEOVER = "takeover"


class WorkItemInteractionSpec(WorktrackerModel):
    """First-class контракт взаимодействия: задаётся создателем задачи (flows HITL).

    Определяет, показывать ли встроенный чат сессии и какие кнопки в композере.
    Хранится на задаче, не в непрозрачном `hook.binding`.
    """

    mode: WorkItemInteractionMode = WorkItemInteractionMode.NONE


class WorkItemConversationRef(WorktrackerModel):
    """Ссылка на разговор flows-сессии для встроенного чата в карточке задачи."""

    session_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    flow_id: str = Field(..., min_length=1)
    branch_id: str = Field(default="default", min_length=1)
    a2a_task_id: str | None = None


class WorkItemInteractionPolicy(WorktrackerModel):
    """Вычисляемая политика композера для карточки задачи (проекция, не персист)."""

    mode: WorkItemInteractionMode = WorkItemInteractionMode.NONE
    can_send: bool = False
    can_complete: bool = False
    conversation: WorkItemConversationRef | None = None


# === Очереди и доски ===


class WorkQueueMember(WorktrackerModel):
    """Участник очереди (user). Роль — relation из OpenFGA."""

    work_queue_id: str = Field(..., min_length=1)
    member: WorkActor
    role: Literal["owner", "member"] = "member"


class WorkQueue(PlatformModel):
    """Очередь. Колонка slug в таблице называется ``slug``."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    work_queue_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    name: str = DbField(max_length=255, min_length=1)
    work_queue_slug: str = DbField(max_length=120, min_length=1, db_column="slug")
    owner_user_id: str = DbField(max_length=100, min_length=1)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    description: str | None = DbField(default=None, db_type="TEXT")

    class Meta:
        is_table: bool = True
        table_name: str = "work_queues"
        unique_together: list[tuple[str, str]] = [("company_id", "work_queue_slug")]

    @classmethod
    async def list_by_work_queue_id(cls, *, limit: int | None) -> list[Self]:
        query = cls.objects.order_by("work_queue_id")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be >= 1")
            query = query.limit(limit)
        return await query.all()

    @classmethod
    async def list_for_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(company_id=company_id).all()

    @classmethod
    async def list_queues(cls, company_id: str) -> list[Self]:
        return await (
            cls.objects.filter(company_id=company_id)
            .order_by("created_at")
            .all()
        )

    @classmethod
    async def by_slug(cls, company_id: str, slug: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_slug=slug,
        ).get_or_none()

    @classmethod
    async def by_id(cls, company_id: str, work_queue_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_id=work_queue_id,
        ).get_or_none()

    @classmethod
    async def create(cls, queue: Self) -> Self:
        return await cls.objects.create(instance=queue)

    @classmethod
    async def delete_for_company(cls, company_id: str, work_queue_id: str) -> int:
        return await cls.objects.filter(
            company_id=company_id,
            work_queue_id=work_queue_id,
        ).delete()


class BoardColumn(WorktrackerModel):
    board_column_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    state: WorkItemState
    position: int = Field(..., ge=0)


def build_generic_board_columns() -> list[BoardColumn]:
    return [
        BoardColumn(
            board_column_id="todo",
            label="To do",
            state=WorkItemState.OPEN,
            position=0,
        ),
        BoardColumn(
            board_column_id="in_progress",
            label="In progress",
            state=WorkItemState.IN_PROGRESS,
            position=1,
        ),
        BoardColumn(
            board_column_id="done",
            label="Done",
            state=WorkItemState.DONE,
            position=2,
        ),
    ]


class Board(PlatformModel):
    """Доска. ``columns`` — JSON этой строки."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    board_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    name: str = DbField(max_length=255, min_length=1)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    namespace: str | None = DbField(default=None, max_length=100)
    board_key: str = DbField(
        default="generic",
        max_length=120,
        description="Логический ключ доски: generic | operator | task | task:<subtype>.",
    )
    columns: list[BoardColumn] = DbField(default_factory=list, db_type="JSONB")

    class Meta:
        is_table: bool = True
        table_name: str = "work_boards"
        indexes: list[Index] = [
            Index(["company_id", "namespace"]),
        ]

    @classmethod
    async def get_board(cls, company_id: str, board_id: str) -> Self:
        board = await cls.objects.filter(
            company_id=company_id,
            board_id=board_id,
        ).get_or_none()
        if board is None:
            raise ValueError(f"Board {board_id!r} not found")
        return board

    @classmethod
    async def company_boards(cls, company_id: str, *, namespace: str | None) -> list[Self]:
        rows = cls.objects.filter(company_id=company_id)
        if namespace is not None:
            rows = rows.filter(namespace=namespace)
        return await rows.order_by("created_at").all()

    @classmethod
    async def create(cls, board: Self) -> Self:
        return await cls.objects.create(instance=board)


class WorkItemCommentRole(StrEnum):
    OPERATOR = "operator"
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class WorkItemComment(PlatformModel):
    """Комментарий задачи. ``author`` и ``files`` — JSON этой строки."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    comment_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    work_item_id: str = DbField(max_length=64, min_length=1, db_index=True)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    author: UserActor | SystemActor = DbField(db_type="JSONB", discriminator="actor_kind")
    created_at: datetime = DbField()
    role: WorkItemCommentRole = DbField(default=WorkItemCommentRole.SYSTEM, max_length=16, db_type="TEXT")
    text: str = DbField(default="", db_type="TEXT")
    files: list[FileRef] = DbField(default_factory=list, db_type="JSONB")

    class Meta:
        is_table: bool = True
        table_name: str = "work_item_comments"

    @classmethod
    async def create(cls, comment: Self) -> Self:
        return await cls.objects.create(instance=comment)

    @classmethod
    async def list_comments(cls, company_id: str, work_item_id: str) -> list[Self]:
        return await (
            cls.objects.filter(company_id=company_id, work_item_id=work_item_id)
            .order_by("created_at")
            .all()
        )


# === Корневая модель ===


class WorkItem(PlatformModel):
    """Каноническая единица работы. Таблица ``work_items``."""

    __database_alias__: ClassVar[str | None] = "worktracker"
    __global_model__: ClassVar[bool] = True

    work_item_id: str = DbField(db_pk=True, max_length=64, min_length=1)
    company_id: str = DbField(max_length=100, min_length=1, db_index=True)
    title: str = DbField(min_length=1, db_type="TEXT")
    created_by: UserActor | SystemActor = DbField(db_type="JSONB", discriminator="actor_kind")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    namespace: str | None = DbField(default=None, max_length=100)
    description: str = DbField(default="", db_type="TEXT")
    kind: WorkItemKind = DbField(default=WorkItemKind.GENERIC, max_length=32, db_type="TEXT")
    state: WorkItemState = DbField(default=WorkItemState.OPEN, max_length=32, db_index=True, db_type="TEXT")
    board_id: str | None = DbField(default=None, max_length=64)
    board_column_id: str | None = DbField(default=None, max_length=64)
    priority: WorkItemPriority = DbField(default=WorkItemPriority.NORMAL, max_length=16, db_type="TEXT")
    due_date: datetime | None = DbField(default=None)
    labels: list[str] = DbField(default_factory=list, db_type="JSONB")
    assignment: UnassignedAssignment | UsersAssignment | QueueAssignment = DbField(
        default_factory=UnassignedAssignment,
        db_type="JSONB",
        discriminator="assignee_kind",
    )
    blocking: bool = DbField(default=False)
    interaction: WorkItemInteractionSpec | None = DbField(default=None, db_type="JSONB")
    hooks: list[WorkItemHook] = DbField(default_factory=list, db_type="JSONB")
    resolution: WorkItemResolution | None = DbField(default=None, db_type="JSONB")
    links: list[
        CrmEntityLink
        | FlowSessionLink
        | SyncMessageLink
        | RagDocumentLink
        | FileLink
        | CalendarEventLink
        | StockTransferLink
        | StockLocationLink
        | WorkItemToWorkItemLink
    ] = DbField(default_factory=list, db_type="JSONB")
    variables: VariableMap = DbField(default_factory=dict, db_type="JSONB")
    attachments: list[FileRef] = DbField(default_factory=list, db_type="JSONB")
    interaction_policy: WorkItemInteractionPolicy | None = None

    class Meta:
        is_table: bool = True
        table_name: str = "work_items"
        indexes: list[Index] = [
            Index(["company_id", "state"]),
            Index(["company_id", "board_id"]),
            Index(["company_id", "namespace"]),
        ]

    def hooks_for(self, event: WorkItemHookEvent) -> list[WorkItemHook]:
        return [hook for hook in self.hooks if hook.event == event]

    def flow_session_link(self) -> FlowSessionLink | None:
        for link in self.links:
            if isinstance(link, FlowSessionLink):
                return link
        return None

    @classmethod
    async def require_in_company(cls, company_id: str, work_item_id: str) -> Self:
        item = await cls.objects.filter(
            company_id=company_id,
            work_item_id=work_item_id,
        ).get_or_none()
        if item is None:
            raise ValueError(f"WorkItem {work_item_id!r} not found")
        return item

    @classmethod
    async def delete_in_company(cls, company_id: str, work_item_id: str) -> bool:
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if work_item_id == "":
            raise ValueError("work_item_id cannot be empty.")
        deleted = await cls.objects.filter(
            company_id=company_id,
            work_item_id=work_item_id,
        ).delete()
        return deleted > 0

    @classmethod
    async def create(cls, item: Self) -> Self:
        return await cls.objects.create(instance=item)

    @classmethod
    async def list_work_items(
        cls,
        company_id: str,
        *,
        board_id: str | None = None,
        namespace: str | None = None,
        kind: WorkItemKind | None = None,
        state: WorkItemState | None = None,
        work_queue_id: str | None = None,
        assignee_user_id: str | None = None,
        assignee_flow_id: str | None = None,
        exclude_terminal: bool = False,
        queue_unclaimed_only: bool = False,
        work_queue_ids: list[str] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WorkItem]:
        sql = work_item_sql(
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
        sql.params.append(limit)
        limit_placeholder = f"${len(sql.params)}"
        sql.params.append(offset)
        offset_placeholder = f"${len(sql.params)}"
        query = (
            "SELECT row_to_json(work_items) AS item FROM work_items "
            + f"WHERE {sql.where()} ORDER BY created_at DESC "
            + f"LIMIT {limit_placeholder} OFFSET {offset_placeholder}"
        )
        rows = await execute_raw(query, sql.params, using="worktracker")
        return [_work_item_from_row(row) for row in rows]

    @classmethod
    async def count_work_items(
        cls,
        company_id: str,
        *,
        board_id: str | None = None,
        namespace: str | None = None,
        kind: WorkItemKind | None = None,
        state: WorkItemState | None = None,
        work_queue_id: str | None = None,
        assignee_user_id: str | None = None,
        assignee_flow_id: str | None = None,
        exclude_terminal: bool = False,
        queue_unclaimed_only: bool = False,
        work_queue_ids: list[str] | None = None,
    ) -> int:
        sql = work_item_sql(
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
        rows = await execute_raw(
            f"SELECT count(*)::int AS total FROM work_items WHERE {sql.where()}",
            sql.params,
            using="worktracker",
        )
        total = require_json_object(rows[0], "work_item_count")["total"]
        if isinstance(total, bool) or not isinstance(total, int):
            raise TypeError("work_item count must be int")
        return total

    @classmethod
    async def find_work_item_by_correlation(
        cls, company_id: str, correlation_id: str
    ) -> Self | None:
        """Поиск WorkItem по correlation_id в hooks[].binding (идемпотентность HITL)."""
        rows = await cls.objects.filter(company_id=company_id).all()
        for row in rows:
            for hook in row.hooks:
                if hook.binding.get("correlation_id") == correlation_id:
                    return row
        return None

    @classmethod
    async def find_work_item_by_crm_entity(
        cls, company_id: str, entity_id: str
    ) -> Self | None:
        """Поиск парного WorkItem по `CrmEntityLink.entity_id` (связь 1:1 с CRM-узлом)."""
        rows = await cls.objects.filter(
            company_id=company_id,
            kind=WorkItemKind.CRM_ACTIVITY,
        ).all()
        for row in rows:
            for link in row.links:
                if isinstance(link, CrmEntityLink) and link.entity_id == entity_id:
                    return row
        return None

    @classmethod
    async def map_work_item_ids_by_crm_entities(
        cls, company_id: str, entity_ids: list[str]
    ) -> dict[str, str]:
        if len(entity_ids) == 0:
            return {}
        wanted = set(entity_ids)
        mapped: dict[str, str] = {}
        rows = await cls.objects.filter(
            company_id=company_id,
            kind=WorkItemKind.CRM_ACTIVITY,
        ).all()
        for row in rows:
            for link in row.links:
                if isinstance(link, CrmEntityLink) and link.entity_id in wanted:
                    mapped[link.entity_id] = row.work_item_id
        return mapped


class _WorkItemSql:
    def __init__(self, company_id: str) -> None:
        self.clauses: list[str] = ["company_id = $1"]
        self.params: list[str | int] = [company_id]

    def add(self, value: str) -> str:
        self.params.append(value)
        return f"${len(self.params)}"

    def where(self) -> str:
        return " AND ".join(self.clauses)


def work_item_sql(
    company_id: str,
    *,
    board_id: str | None,
    namespace: str | None,
    kind: WorkItemKind | None,
    state: WorkItemState | None,
    work_queue_id: str | None,
    assignee_user_id: str | None,
    assignee_flow_id: str | None,
    exclude_terminal: bool,
    queue_unclaimed_only: bool,
    work_queue_ids: list[str] | None,
) -> _WorkItemSql:
    sql = _WorkItemSql(company_id)
    if board_id is not None:
        sql.clauses.append(f"board_id = {sql.add(board_id)}")
    if namespace is not None:
        sql.clauses.append(f"namespace = {sql.add(namespace)}")
    if kind is not None:
        sql.clauses.append(f"kind = {sql.add(kind.value)}")
    if state is not None:
        sql.clauses.append(f"state = {sql.add(state.value)}")
    if exclude_terminal:
        placeholders = [sql.add(item.value) for item in TERMINAL_WORK_ITEM_STATES]
        sql.clauses.append(f"state NOT IN ({', '.join(placeholders)})")
    if work_queue_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
        )
        sql.clauses.append(f"assignment->>'work_queue_id' = {sql.add(work_queue_id)}")
    if assignee_flow_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.USERS.value)}"
        )
        user_ids_json = sql.add(json.dumps([flow_employee_user_id(assignee_flow_id)]))
        sql.clauses.append(f"assignment->'user_ids' @> {user_ids_json}::jsonb")
    if assignee_user_id is not None:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.USERS.value)}"
        )
        sql.clauses.append(
            f"assignment->'user_ids' @> {sql.add(json.dumps([assignee_user_id]))}::jsonb"
        )
    if queue_unclaimed_only:
        sql.clauses.append(
            f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
        )
        sql.clauses.append("assignment->>'claimed_by_user_id' IS NULL")
    if work_queue_ids is not None:
        if len(work_queue_ids) == 0:
            sql.clauses.append("FALSE")
        else:
            placeholders = ", ".join(sql.add(queue_id) for queue_id in work_queue_ids)
            sql.clauses.append(
                f"assignment->>'assignee_kind' = {sql.add(AssigneeKind.QUEUE.value)}"
            )
            sql.clauses.append(f"assignment->>'work_queue_id' IN ({placeholders})")
            sql.clauses.append("assignment->>'claimed_by_user_id' IS NULL")
    return sql


def _work_item_from_row(row: object) -> WorkItem:
    parsed = require_json_object(row, "work_item")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "work_item")
    else:
        payload = require_json_object(raw_item, "work_item")
    return WorkItem.model_validate(payload)


def build_conversation_ref(item: WorkItem) -> WorkItemConversationRef | None:
    """Строит ссылку на разговор из типизированного FlowSessionLink задачи."""
    link = item.flow_session_link()
    if link is None:
        return None
    if link.context_id is None or link.flow_id is None:
        return None
    return WorkItemConversationRef(
        session_id=link.session_id,
        context_id=link.context_id,
        flow_id=link.flow_id,
        branch_id=link.branch_id or "default",
        a2a_task_id=link.a2a_task_id,
    )


def build_interaction_policy(
    item: WorkItem,
    *,
    operator_authorized: bool,
) -> WorkItemInteractionPolicy:
    """Вычисляет политику композера карточки задачи.

    Оба HITL-режима: composer доступен, если оператор авторизован и задача не terminal.
    single_reply: Submit = complete + closing reply (лейбл «Ответить и завершить»).
    takeover: Submit = ask; отдельная кнопка Complete.
    Прочее: mode=none (обычная задача, встроенного чата нет).
    """
    spec = item.interaction
    if spec is None or spec.mode == WorkItemInteractionMode.NONE:
        return WorkItemInteractionPolicy(mode=WorkItemInteractionMode.NONE)
    is_terminal = item.state in TERMINAL_WORK_ITEM_STATES
    active = operator_authorized and not is_terminal
    return WorkItemInteractionPolicy(
        mode=spec.mode,
        can_send=active,
        can_complete=active,
        conversation=build_conversation_ref(item),
    )
