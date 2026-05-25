"""Модели InterruptData: strict union, strict envelope, parse external dict."""

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


def test_interrupt_data_requires_typed_envelope() -> None:
    ir = InterruptData.model_validate(
        {
            "body": {"kind": "user_message", "question": "Name?"},
            "system": {"task_id": "t1", "path": [{"type": "tool", "id": "ask_user"}]},
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
        _ = InterruptData.model_validate({"foo": 1})


def test_parse_external_user_message_requires_kind() -> None:
    b = parse_interrupt_body_from_external_dict(
        {"kind": "user_message", "question": "Need input"}
    )
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
    with pytest.raises(ValueError, match="kind"):
        _ = parse_interrupt_body_from_external_dict({"question": "Need input"})


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
        _ = FlowInterrupt()
    with pytest.raises(ValueError):
        _ = FlowInterrupt(question="", body=None)


def test_interrupt_to_response_dict_roundtrip() -> None:
    ir = InterruptData(
        body=UserMessageInterrupt(question="q"),
        system=InterruptSystemContext(task_id="t"),
    )
    payload = interrupt_to_response_dict(ir)
    assert "question" not in payload
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
