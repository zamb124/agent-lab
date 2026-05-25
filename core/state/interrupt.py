"""
Типизированные данные прерывания (HITL): StrEnum, discriminated union, системный конверт.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from core.clients.llm.messages import LLMToolCall
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object


class InterruptKind(StrEnum):
    USER_MESSAGE = "user_message"
    OPERATOR_TASK = "operator_task"
    OAUTH_REQUIRED = "oauth_required"


class HandoffMode(StrEnum):
    SINGLE_REPLY = "single_reply"
    TAKEOVER = "takeover"


class UserMessageInterrupt(StrictBaseModel):
    """Запрос ввода у пользователя в чате (аналог ask_user)."""

    kind: Literal[InterruptKind.USER_MESSAGE] = InterruptKind.USER_MESSAGE
    question: str = Field(..., min_length=1)


class OperatorTaskInterrupt(StrictBaseModel):
    """Пауза до действия оператора; в чате пользователю показывается question (статусная строка)."""

    kind: Literal[InterruptKind.OPERATOR_TASK] = InterruptKind.OPERATOR_TASK
    question: str = Field(
        ...,
        min_length=1,
        description="Текст для UI конечного пользователя (без внутренних деталей задачи)",
    )
    task_title: str = Field(..., min_length=1)
    assignee_queue: str = Field(..., min_length=1)
    handoff_mode: HandoffMode = Field(
        default=HandoffMode.SINGLE_REPLY,
        description="single_reply — один ответ оператора; takeover — полный перехват диалога",
    )
    operator_task_id: str | None = Field(
        default=None,
        description="ID строки OperatorTasks (для user-reply в takeover)",
    )
    handoff_command_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=1)
    node_id: str = Field(..., min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)


class OAuthInterrupt(StrictBaseModel):
    """Пауза до завершения OAuth-авторизации пользователя во внешнем сервисе."""

    kind: Literal[InterruptKind.OAUTH_REQUIRED] = InterruptKind.OAUTH_REQUIRED
    question: str = Field(..., min_length=1)
    auth_url: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)


InterruptBody = Annotated[
    UserMessageInterrupt | OperatorTaskInterrupt | OAuthInterrupt,
    Field(discriminator="kind"),
]

_INTERRUPT_BODY_ADAPTER: TypeAdapter[InterruptBody] = TypeAdapter(InterruptBody)


class InterruptSystemContext(StrictBaseModel):
    """Служебные поля прерывания (путь, task_id, tool_call)."""

    tool_call: LLMToolCall | None = None
    path: list[JsonObject] = Field(default_factory=list)
    task_id: str | None = None
    context_id: str | None = None


def parse_interrupt_body_from_external_dict(raw: JsonObject) -> InterruptBody:
    """
    Разбор тела interrupt с внешнего API или inline-ответа tool.
    Внешний interrupt обязан быть типизированным discriminated union.
    """
    if "kind" not in raw:
        raise ValueError("interrupt.kind is required")
    return _INTERRUPT_BODY_ADAPTER.validate_python(raw)


def interrupt_to_response_dict(ir: "InterruptData") -> JsonObject:
    """Сериализация для HTTP/TaskIQ: строгий InterruptData envelope."""
    return require_json_object(ir.model_dump(mode="json"), "interrupt")


def interrupt_body_public_question(body: InterruptBody) -> str:
    """Текст для A2A message / пуша / InterruptData.question."""
    if isinstance(body, UserMessageInterrupt):
        return body.question
    if isinstance(body, OperatorTaskInterrupt):
        return body.question
    return body.question


class InterruptData(StrictBaseModel):
    """Корневая модель прерывания в ExecutionState."""

    body: InterruptBody
    system: InterruptSystemContext = Field(default_factory=InterruptSystemContext)
    correlation_id: UUID | None = None

    @property
    def question(self) -> str:
        return interrupt_body_public_question(self.body)

    @model_validator(mode="before")
    @classmethod
    def _validate_interrupt_envelope(
        cls,
        data: object,
    ) -> object:
        if isinstance(data, InterruptData):
            return data
        if not isinstance(data, dict):
            raise ValueError(f"InterruptData: ожидается dict, получено {type(data)}")
        if "body" not in data or "system" not in data:
            raise ValueError("InterruptData requires body and system")
        return cast(object, data)


__all__ = [
    "InterruptKind",
    "HandoffMode",
    "UserMessageInterrupt",
    "OperatorTaskInterrupt",
    "OAuthInterrupt",
    "InterruptBody",
    "InterruptSystemContext",
    "InterruptData",
    "interrupt_body_public_question",
    "interrupt_to_response_dict",
    "parse_interrupt_body_from_external_dict",
]
