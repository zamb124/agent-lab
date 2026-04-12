"""
Типизированные данные прерывания (HITL): StrEnum, discriminated union, системный конверт.

Миграция legacy-словарей {question, context?} — только через model_validator InterruptData.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union, assert_never
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from core.models import StrictBaseModel


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
    operator_task_id: Optional[str] = Field(
        default=None,
        description="ID строки OperatorTasks (для user-reply в takeover)",
    )


class OAuthInterrupt(StrictBaseModel):
    """Пауза до завершения OAuth-авторизации пользователя во внешнем сервисе."""

    kind: Literal[InterruptKind.OAUTH_REQUIRED] = InterruptKind.OAUTH_REQUIRED
    question: str = Field(..., min_length=1)
    auth_url: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)


InterruptBody = Annotated[
    Union[UserMessageInterrupt, OperatorTaskInterrupt, OAuthInterrupt],
    Field(discriminator="kind"),
]

_INTERRUPT_BODY_ADAPTER: TypeAdapter[InterruptBody] = TypeAdapter(InterruptBody)


class InterruptSystemContext(StrictBaseModel):
    """Служебные поля прерывания (путь, task_id, tool_call)."""

    tool_call: Optional[Dict[str, Any]] = None
    path: List[Dict[str, Any]] = Field(default_factory=list)
    task_id: Optional[str] = None
    context_id: Optional[str] = None


def system_from_legacy_context(ctx: Any) -> InterruptSystemContext:
    """Единственная точка разбора старого interrupt.context при миграции."""
    if ctx is None:
        return InterruptSystemContext()
    if not isinstance(ctx, dict):
        raise ValueError(
            f"legacy interrupt.context ожидается dict или None, получено {type(ctx)}"
        )
    raw_path = ctx.get("path")
    path: List[Dict[str, Any]]
    if raw_path is None:
        path = []
    elif isinstance(raw_path, list):
        path = [p for p in raw_path if isinstance(p, dict)]
    else:
        raise ValueError("legacy interrupt.context.path должен быть list или отсутствовать")
    return InterruptSystemContext(
        tool_call=ctx.get("tool_call"),
        path=path,
        task_id=ctx.get("task_id"),
        context_id=ctx.get("context_id"),
    )


def parse_interrupt_body_from_external_dict(raw: Dict[str, Any]) -> InterruptBody:
    """
    Разбор тела interrupt с внешнего API или inline-ответа tool.
    Без kind — только user_message и обязательный question.
    """
    if "kind" not in raw:
        if "question" not in raw:
            raise ValueError("interrupt: без kind требуется непустой question")
        q = raw["question"]
        if not isinstance(q, str) or not q.strip():
            raise ValueError("interrupt.question должен быть непустой строкой")
        return UserMessageInterrupt(question=q.strip())
    return _INTERRUPT_BODY_ADAPTER.validate_python(raw)


def interrupt_to_response_dict(ir: "InterruptData") -> Dict[str, Any]:
    """Сериализация для HTTP/TaskIQ: полный объект + поле question для совместимости клиентов."""
    data = ir.model_dump(mode="json")
    data["question"] = ir.question
    return data


def interrupt_body_public_question(body: InterruptBody) -> str:
    """Текст для A2A message / пуша / legacy .question на InterruptData."""
    match body:
        case UserMessageInterrupt(question=q):
            return q
        case OperatorTaskInterrupt(question=q):
            return q
        case OAuthInterrupt(question=q):
            return q
        case _ as unreachable:
            assert_never(unreachable)


class InterruptData(StrictBaseModel):
    """Корневая модель прерывания в ExecutionState."""

    body: InterruptBody
    system: InterruptSystemContext = Field(default_factory=InterruptSystemContext)
    correlation_id: Optional[UUID] = None

    @property
    def question(self) -> str:
        return interrupt_body_public_question(self.body)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy(cls, data: Any) -> Any:
        if data is None or isinstance(data, InterruptData):
            return data
        if not isinstance(data, dict):
            raise ValueError(f"InterruptData: ожидается dict, получено {type(data)}")
        if "body" in data:
            cleaned = dict(data)
            cleaned.pop("question", None)
            if "system" not in cleaned:
                raise ValueError("InterruptData: вместе с body обязательно поле system")
            return cleaned
        if "question" in data:
            q = data["question"]
            if not isinstance(q, str) or not q.strip():
                raise ValueError("legacy InterruptData: question должен быть непустой строкой")
            ctx = data.get("context")
            system = system_from_legacy_context(ctx)
            out: Dict[str, Any] = {
                "body": {
                    "kind": InterruptKind.USER_MESSAGE,
                    "question": q.strip(),
                },
                "system": system.model_dump(mode="json"),
            }
            cid = data.get("correlation_id")
            if cid is not None:
                out["correlation_id"] = cid
            return out
        raise ValueError(
            "InterruptData: неизвестная форма (нужны body+system или legacy question)"
        )


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
    "system_from_legacy_context",
]
