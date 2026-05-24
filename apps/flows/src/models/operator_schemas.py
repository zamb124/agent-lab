"""
Pydantic-схемы для API операторских очередей и задач.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.state.interrupt import HandoffMode
from core.types import JsonObject


class OperatorTaskStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    USER_DIALOG = "user_dialog"
    AWAITING_AGENT = "awaiting_agent"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OperatorQueueCreate(StrictBaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    description: str | None = None


class OperatorQueuePatch(StrictBaseModel):
    name: str | None = Field(None, min_length=1)
    description: str | None = None


class OperatorQueueOut(StrictBaseModel):
    id: str
    company_id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    i_am_member: bool = False


class OperatorMemberAdd(StrictBaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(default="agent", min_length=1)


class OperatorTaskOut(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    id: str
    company_id: str
    queue_id: str
    status: OperatorTaskStatus
    session_id: str
    end_user_id: str
    flow_id: str
    branch_id: str
    flow_display_name: str = Field(
        ...,
        description="Название flow из конфига; при отсутствии конфига — flow_id",
    )
    skill_display_name: str = Field(
        ...,
        description="Название skill из конфига; при отсутствии — branch_id",
    )
    handoff_title: str | None = Field(
        default=None,
        description="Заголовок из interrupt_snapshot (handoff)",
    )
    handoff_message_preview: str | None = Field(
        default=None,
        description="Краткий текст вопроса пользователю из interrupt_snapshot",
    )
    handoff_mode: HandoffMode = Field(
        default=HandoffMode.SINGLE_REPLY,
        description="Режим оператора: single_reply или takeover",
    )
    a2a_task_id: str | None = None
    context_id: str | None = None
    correlation_id: str | None = None
    claimed_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None



class OperatorInterruptSnapshot(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    question: str = Field(..., min_length=1)
    task_title: str = Field(..., min_length=1)
    assignee_queue: str = Field(..., min_length=1)
    queue_id: str = Field(..., min_length=1)
    handoff_mode: HandoffMode = HandoffMode.SINGLE_REPLY


class OperatorDialogLogEntry(StrictBaseModel):
    role: Literal["operator", "user"]
    text: str = ""
    ts: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)


class OperatorResolutionPayload(StrictBaseModel):
    text: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)


class OperatorTaskDetailOut(StrictBaseModel):
    task: OperatorTaskOut
    interrupt_snapshot: OperatorInterruptSnapshot
    resolution_payload: OperatorResolutionPayload | None = None
    dialog_log: list[OperatorDialogLogEntry] = Field(default_factory=list)
    dialog_messages: list[JsonObject] = Field(default_factory=list)


class OperatorTaskPatch(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    status: OperatorTaskStatus


class OperatorTaskMessageBody(StrictBaseModel):
    text: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)


class OperatorTaskCompleteBody(StrictBaseModel):
    resolution: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)
