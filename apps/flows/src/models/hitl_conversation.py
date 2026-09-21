"""Контракты встроенного чата HITL-задачи (проекция ExecutionState.messages).

Оператор в карточке WorkItem(operator_handoff) видит технически тот же разговор
сессии, что и пользователь. Проекция строится из `ExecutionState.messages`,
курсор — монотонный индекс сообщения для realtime-replay.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from core.models import StrictBaseModel
from core.worktracker.models import WorkItemInteractionPolicy


class ConversationTurnRole(StrEnum):
    USER = "user"
    OPERATOR = "operator"
    AGENT = "agent"
    SYSTEM = "system"


class ConversationTurn(StrictBaseModel):
    """Один turn разговора в проекции чата HITL-задачи."""

    cursor: int = Field(..., ge=1, description="Монотонный индекс turn (1-based)")
    message_id: str = Field(..., min_length=1)
    role: ConversationTurnRole
    text: str = ""
    file_ids: list[str] = Field(default_factory=list)


class ConversationSnapshot(StrictBaseModel):
    """Снимок разговора для карточки задачи: turns + курсор + политика композера."""

    work_item_id: str = Field(..., min_length=1)
    turns: list[ConversationTurn] = Field(default_factory=list)
    cursor: int = Field(default=0, ge=0, description="Курсор последнего turn (0 = пусто)")
    policy: WorkItemInteractionPolicy


class HitlConversationWorkItemPayload(StrictBaseModel):
    work_item_id: str = ""


class OperatorMessageRequest(StrictBaseModel):
    work_item_id: str = ""
    text: str = ""
    idempotency_key: str = Field(..., min_length=1)
    file_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_text_or_files(self) -> OperatorMessageRequest:
        clean = self.text.strip()
        file_ids = [fid.strip() for fid in self.file_ids if fid.strip()]
        if clean == "" and len(file_ids) == 0:
            raise ValueError("text or file_ids is required")
        if clean == self.text and file_ids == self.file_ids:
            return self
        return self.model_copy(update={"text": clean, "file_ids": file_ids})


HITL_CONVERSATION_TURN_APPENDED = "flows/hitl_conversation/turn_appended"


class ConversationTurnAppendedEvent(StrictBaseModel):
    """Push-событие нового turn для встроенного чата карточки задачи.

    Доставляется через `platform:events` -> WS; UI-slice дописывает turn по
    `cursor` (монотонный), дедуп по `message_id`.
    """

    work_item_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    turn: ConversationTurn
