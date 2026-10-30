"""
Доменные модели ядра задач WorkItem.

Дискриминированные union строятся по образцу `apps/flows/src/state/interrupt.py`:
поле-дискриминатор `Literal[Enum.MEMBER] = Enum.MEMBER`, обёртка через
`Annotated[..., Field(discriminator=...)]`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field, model_validator

from core.files.file_attachments import minimal_file_refs_from_file_ids
from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, require_json_array, require_json_object


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
    def _stored_file_ids(cls, value: JsonValue) -> JsonValue:
        def has_legacy_file_ids(raw: JsonValue) -> bool:
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

