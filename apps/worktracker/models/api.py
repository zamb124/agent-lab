"""Request/response модели API ядра задач WorkItem."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.variables.models import VariableMap
from core.worktracker.models import (
    BoardColumn,
    WorkActor,
    WorkItemAssignment,
    WorkItemKind,
    WorkItemLink,
    WorkItemPriority,
    WorkItemState,
)


class WorkItemCreateRequest(StrictBaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    kind: WorkItemKind = WorkItemKind.GENERIC
    namespace: str | None = None
    board_id: str | None = None
    board_column_id: str | None = None
    priority: WorkItemPriority = WorkItemPriority.NORMAL
    due_date: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    assignment: WorkItemAssignment | None = None
    blocking: bool = False
    links: list[WorkItemLink] = Field(default_factory=list)
    variables: VariableMap = Field(default_factory=dict)
    attachments: list[FileRef] = Field(default_factory=list)


class WorkItemUpdateRequest(StrictBaseModel):
    title: str | None = None
    description: str | None = None
    priority: WorkItemPriority | None = None
    due_date: datetime | None = None
    labels: list[str] | None = None
    links: list[WorkItemLink] | None = None
    variables: VariableMap | None = None
    attachments: list[FileRef] | None = None


class WorkItemAssignRequest(StrictBaseModel):
    assignment: WorkItemAssignment


class WorkItemMoveRequest(StrictBaseModel):
    board_column_id: str | None = None
    state: WorkItemState | None = None


class WorkItemCommentRequest(StrictBaseModel):
    text: str = ""
    files: list[FileRef] = Field(default_factory=list)


class WorkItemCompleteRequest(StrictBaseModel):
    resolution_text: str = ""
    resolution_files: list[FileRef] = Field(default_factory=list)
    terminal_state: WorkItemState = WorkItemState.DONE


class WorkQueueCreateRequest(StrictBaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    description: str | None = None


class WorkQueueUpdateRequest(StrictBaseModel):
    name: str | None = None
    description: str | None = None


class WorkQueueMemberAddRequest(StrictBaseModel):
    member: WorkActor
    role: str = "member"


class WorkQueueMemberRemoveRequest(StrictBaseModel):
    member: WorkActor


class BoardCreateRequest(StrictBaseModel):
    name: str = Field(..., min_length=1)
    namespace: str | None = None
    board_key: str = "generic"
    columns: list[BoardColumn] = Field(default_factory=list)


class BoardUpdateRequest(StrictBaseModel):
    name: str | None = None
    columns: list[BoardColumn] | None = None


class WorkItemMineSummaryResponse(StrictBaseModel):
    assigned_open_count: int = Field(..., ge=0)
    queue_inbox_count: int = Field(..., ge=0)
