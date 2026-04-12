"""Модели InterruptData: union, миграция legacy, parse внешнего dict."""

import pytest
from pydantic import ValidationError

from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.state.interrupt import (
    InterruptData,
    InterruptKind,
    InterruptSystemContext,
    OperatorTaskInterrupt,
    UserMessageInterrupt,
    interrupt_body_public_question,
    interrupt_to_response_dict,
    parse_interrupt_body_from_external_dict,
)


def test_user_message_interrupt_question() -> None:
    b = UserMessageInterrupt(question="  hi  ")
    assert b.question == "hi"


def test_interrupt_data_legacy_question_context() -> None:
    ir = InterruptData.model_validate(
        {
            "question": "Name?",
            "context": {"task_id": "t1", "path": [{"type": "tool", "id": "ask_user"}]},
        }
    )
    assert ir.body.kind == InterruptKind.USER_MESSAGE
    assert isinstance(ir.body, UserMessageInterrupt)
    assert ir.body.question == "Name?"
    assert ir.system.task_id == "t1"
    assert len(ir.system.path) == 1
    assert ir.question == "Name?"


def test_interrupt_data_rejects_unknown_shape() -> None:
    with pytest.raises(ValidationError):
        InterruptData.model_validate({"foo": 1})


def test_parse_external_legacy_question_only() -> None:
    b = parse_interrupt_body_from_external_dict({"question": "Need input"})
    assert isinstance(b, UserMessageInterrupt)
    assert b.question == "Need input"


def test_parse_external_operator_task() -> None:
    b = parse_interrupt_body_from_external_dict(
        {
            "kind": "operator_task",
            "question": "Ждём специалиста",
            "task_title": "Проверка",
            "assignee_queue": "l1",
        }
    )
    assert isinstance(b, OperatorTaskInterrupt)
    assert b.assignee_queue == "l1"


def test_parse_external_empty_question_rejected() -> None:
    with pytest.raises(ValueError):
        parse_interrupt_body_from_external_dict({})


def test_flow_interrupt_question_or_body() -> None:
    e1 = FlowInterrupt(question="x")
    assert e1.body.kind == InterruptKind.USER_MESSAGE
    e2 = FlowInterrupt(
        body=OperatorTaskInterrupt(
            question="u",
            task_title="t",
            assignee_queue="q",
        )
    )
    assert e2.body.kind == InterruptKind.OPERATOR_TASK
    with pytest.raises(ValueError):
        FlowInterrupt()
    with pytest.raises(ValueError):
        FlowInterrupt(question="", body=None)


def test_interrupt_to_response_dict_roundtrip() -> None:
    ir = InterruptData(
        body=UserMessageInterrupt(question="q"),
        system=InterruptSystemContext(task_id="t"),
    )
    payload = interrupt_to_response_dict(ir)
    assert payload["question"] == "q"
    restored = InterruptData.model_validate(payload)
    assert restored.question == "q"


def test_interrupt_body_public_question_match() -> None:
    assert interrupt_body_public_question(UserMessageInterrupt(question="a")) == "a"
    assert (
        interrupt_body_public_question(
            OperatorTaskInterrupt(
                question="status",
                task_title="t",
                assignee_queue="q",
            )
        )
        == "status"
    )
