"""
Доменные модели ядра задач WorkItem.

Дискриминированные union строятся по образцу `core/state/interrupt.py`:
поле-дискриминатор `Literal[Enum.MEMBER] = Enum.MEMBER`, обёртка через
`Annotated[..., Field(discriminator=...)]`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field

from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.types import JsonObject
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
    AGENT = "agent"
    SYSTEM = "system"


class UserActor(WorktrackerModel):
    actor_kind: Literal[ActorKind.USER] = ActorKind.USER
    user_id: str = Field(..., min_length=1)


class AgentActor(WorktrackerModel):
    actor_kind: Literal[ActorKind.AGENT] = ActorKind.AGENT
    flow_id: str = Field(..., min_length=1)
    session_id: str | None = None


class SystemActor(WorktrackerModel):
    actor_kind: Literal[ActorKind.SYSTEM] = ActorKind.SYSTEM


WorkActor = Annotated[
    UserActor | AgentActor | SystemActor,
    Field(discriminator="actor_kind"),
]


# === Assignment (кому назначена работа) ===


class AssigneeKind(StrEnum):
    UNASSIGNED = "unassigned"
    USERS = "users"
    QUEUE = "queue"
    AGENT = "agent"


class UnassignedAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.UNASSIGNED] = AssigneeKind.UNASSIGNED


class UsersAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.USERS] = AssigneeKind.USERS
    user_ids: list[str] = Field(..., min_length=1)


class QueueAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.QUEUE] = AssigneeKind.QUEUE
    work_queue_id: str = Field(..., min_length=1)
    claimed_by_user_id: str | None = None


class AgentAssignment(WorktrackerModel):
    assignee_kind: Literal[AssigneeKind.AGENT] = AssigneeKind.AGENT
    flow_id: str = Field(..., min_length=1)
    branch_id: str | None = None


WorkItemAssignment = Annotated[
    UnassignedAssignment | UsersAssignment | QueueAssignment | AgentAssignment,
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
    """Generic-хук жизненного цикла: апп-слой дёргает `{service, path}` на событии.

    Ядро не знает семантику; `binding` — непрозрачные данные потребителя
    (например flows-сессия для возобновления durable workflow).
    """

    event: WorkItemHookEvent
    service: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    binding: JsonObject = Field(default_factory=dict)


class WorkItemResolution(WorktrackerModel):
    text: str = ""
    files: list[FileRef] = Field(default_factory=list)
    resolved_by: WorkActor | None = None


# === Очереди и доски ===


class WorkQueueMember(WorktrackerModel):
    """Участник очереди — пользователь или агент (flow). Доступ + роль."""

    work_queue_id: str = Field(..., min_length=1)
    member: WorkActor
    role: str = "member"


class WorkQueue(WorktrackerModel):
    work_queue_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    work_queue_slug: str = Field(..., min_length=1)
    description: str | None = None
    created_at: datetime
    updated_at: datetime


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


class Board(WorktrackerModel):
    board_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str | None = None
    board_key: str = Field(
        default="generic",
        description="Логический ключ доски: generic | operator | task | task:<subtype>.",
    )
    name: str = Field(..., min_length=1)
    columns: list[BoardColumn] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkItemCommentRole(StrEnum):
    OPERATOR = "operator"
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"


class WorkItemComment(WorktrackerModel):
    comment_id: str = Field(..., min_length=1)
    work_item_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    author: WorkActor
    role: WorkItemCommentRole = WorkItemCommentRole.SYSTEM
    text: str = ""
    files: list[FileRef] = Field(default_factory=list)
    created_at: datetime


# === Корневая модель ===


class WorkItem(WorktrackerModel):
    """Каноническая единица работы платформы."""

    work_item_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    namespace: str | None = None
    title: str = Field(..., min_length=1)
    description: str = ""
    kind: WorkItemKind = WorkItemKind.GENERIC
    state: WorkItemState = WorkItemState.OPEN
    board_id: str | None = None
    board_column_id: str | None = None
    priority: WorkItemPriority = WorkItemPriority.NORMAL
    due_date: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    created_by: WorkActor
    assignment: WorkItemAssignment = Field(default_factory=UnassignedAssignment)
    blocking: bool = False
    hooks: list[WorkItemHook] = Field(default_factory=list)
    resolution: WorkItemResolution | None = None
    links: list[WorkItemLink] = Field(default_factory=list)
    variables: VariableMap = Field(default_factory=dict)
    attachments: list[FileRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    def hooks_for(self, event: WorkItemHookEvent) -> list[WorkItemHook]:
        return [hook for hook in self.hooks if hook.event == event]
