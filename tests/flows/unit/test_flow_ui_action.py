"""Приём ``ui-action``: поля интерфейса становятся полями ExecutionState, файлы — ``FileRef``."""

from __future__ import annotations

from typing import cast

import pytest
from a2a.types import Message, Part, Role

from apps.flows.src.flow_ui.action import (
    apply_flow_ui_action,
    render_ui_action_markdown,
    ui_action_from_message,
    validate_flow_ui_action,
)
from apps.flows.src.flow_ui.projection import assert_fields_outside_redacted
from apps.flows.src.state import ExecutionState
from core.a2a.codec import value_from_json
from core.files.file_ref import FileRef
from core.ui_document.document import FlowUIDocument, FlowUIMarkdownText
from core.ui_document.protocol import FLOW_UI_ACTION_MEDIA_TYPE, FlowUIActionMessage
from core.types import JsonObject

FILE_PAYLOAD = {
    "file_id": "file_e82cc35e2182",
    "url": "/flows/api/v1/files/download/file_e82cc35e2182",
    "content_type": "image/jpeg",
    "file_size": 1742772,
    "original_name": "IMG_2444.JPG",
}


def _action_part(payload: dict[str, object]) -> Part:
    return Part(
        data=value_from_json(cast(JsonObject, payload)), media_type=FLOW_UI_ACTION_MEDIA_TYPE
    )


def _state() -> ExecutionState:
    return ExecutionState(
        task_id="task-1", context_id="ctx-1", user_id="user-1", session_id="flow-1:ctx-1"
    )


def _interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "title": "Lead",
                    "blocks": [
                        {
                            "type": "text_input",
                            "block_id": "email",
                            "field": "email",
                            "label": "Email",
                            "required": True,
                        },
                        {
                            "type": "number_input",
                            "block_id": "headcount",
                            "field": "lead.headcount",
                            "label": "Headcount",
                        },
                        {
                            "type": "select",
                            "block_id": "plan",
                            "field": "plan",
                            "label": "Plan",
                            "options": [
                                {"value": "free", "label": "Free"},
                                {"value": "pro", "label": "Pro"},
                            ],
                        },
                        {
                            "type": "switch",
                            "block_id": "consent",
                            "field": "consent",
                            "label": "Consent",
                        },
                        {
                            "type": "file_upload",
                            "block_id": "attachments",
                            "field": "attachments",
                            "label": "Files",
                        },
                        {"type": "slot", "block_id": "summary"},
                        {
                            "type": "button",
                            "block_id": "submit",
                            "label": "Send",
                            "action": {"name": "submit"},
                        },
                    ],
                },
                {
                    "page_id": "extra",
                    "title": "Extra",
                    "blocks": [
                        {
                            "type": "text_input",
                            "block_id": "note",
                            "field": "note",
                            "label": "Note",
                        },
                    ],
                },
            ],
        }
    )


def _action(**fields: object) -> FlowUIActionMessage:
    return FlowUIActionMessage.model_validate(
        {"action": "submit", "source": "submit", "fields": fields, "payload": {"origin": "test"}}
    )


def test_ui_action_writes_fields_event_and_markdown_content() -> None:
    state = _state()
    files = apply_flow_ui_action(
        state,
        _action(
            email="a@b.c",
            **{"lead.headcount": 12},
            plan="pro",
            consent=True,
            attachments=[FILE_PAYLOAD],
        ),
        _interface(),
    )
    assert state.email == "a@b.c"
    assert state.lead == {"headcount": 12}
    assert state.plan == "pro"
    assert state.consent is True
    assert state.attachments == [FileRef.model_validate(FILE_PAYLOAD).model_dump(mode="json")]
    assert state.ui_action is not None
    assert state.ui_action.name == "submit"
    assert state.ui_action.source == "submit"
    assert state.ui_action.payload == {"origin": "test"}
    assert state.content == (
        "Действие: submit\n- Email: a@b.c\n- Headcount: 12\n- Plan: pro\n- Consent: да\n- Files: IMG_2444.JPG"
    )
    assert [ref.file_id for ref in files] == ["file_e82cc35e2182"]
    assert files[0].original_name == "IMG_2444.JPG"


def test_markdown_follows_interface_order_not_message_order() -> None:
    validated = validate_flow_ui_action(_action(plan="free", email="x@y.z"), _interface(), {})
    assert validated.content == "Действие: submit\n- Email: x@y.z\n- Plan: free"
    assert render_ui_action_markdown(_action(), validated.writable) == "Действие: submit"


def test_required_field_of_source_page_must_be_filled() -> None:
    with pytest.raises(ValueError, match="required field 'email' is empty"):
        validate_flow_ui_action(_action(plan="free"), _interface(), {})
    with pytest.raises(ValueError, match="required field 'email' is empty"):
        validate_flow_ui_action(_action(email=""), _interface(), {})


def test_unknown_field_and_wrong_types_are_rejected() -> None:
    interface = _interface()
    with pytest.raises(ValueError, match="field 'phone' is not an input"):
        validate_flow_ui_action(_action(email="a@b.c", phone="1"), interface, {})
    with pytest.raises(ValueError, match="expected number"):
        validate_flow_ui_action(_action(email="a@b.c", **{"lead.headcount": "12"}), interface, {})
    with pytest.raises(ValueError, match="unknown option 'enterprise'"):
        validate_flow_ui_action(_action(email="a@b.c", plan="enterprise"), interface, {})
    with pytest.raises(ValueError, match="expected boolean"):
        validate_flow_ui_action(_action(email="a@b.c", consent="yes"), interface, {})
    with pytest.raises(ValueError, match="expected list of files"):
        validate_flow_ui_action(_action(email="a@b.c", attachments=FILE_PAYLOAD), interface, {})


def test_fields_of_other_pages_and_rendered_slots_are_writable() -> None:
    state = _state()
    state.ui_slots = {
        "summary": [
            FlowUIMarkdownText(block_id="hint", markdown="hi"),
            *FlowUIDocument.model_validate(
                {
                    "start_page_id": "p",
                    "pages": [
                        {
                            "page_id": "p",
                            "title": "p",
                            "blocks": [
                                {
                                    "type": "text_input",
                                    "block_id": "city",
                                    "field": "city",
                                    "label": "City",
                                }
                            ],
                        }
                    ],
                }
            ).blocks(),
        ]
    }
    _ = apply_flow_ui_action(state, _action(email="a@b.c", note="n", city="Moscow"), _interface())
    assert state.note == "n"
    assert state.city == "Moscow"


def test_action_without_fields_only_records_event() -> None:
    state = _state()
    message = FlowUIActionMessage.model_validate(
        {"action": "send", "source": "conversation", "payload": {"text": "hello"}}
    )
    assert apply_flow_ui_action(state, message, _interface()) == []
    assert state.content == "Действие: send"
    assert state.ui_action is not None
    assert state.ui_action.payload == {"text": "hello"}


def test_ui_action_part_is_extracted_from_message() -> None:
    payload = {"action": "submit", "source": "submit", "fields": {"email": "a@b.c"}, "payload": {}}
    message = Message(
        message_id="m-1",
        role=Role.ROLE_USER,
        parts=[_action_part(payload)],
    )
    action = ui_action_from_message(message)
    assert action is not None
    assert action.fields == {"email": "a@b.c"}
    assert (
        ui_action_from_message(
            Message(message_id="m-2", role=Role.ROLE_USER, parts=[Part(text="hi")])
        )
        is None
    )
    with pytest.raises(ValueError, match="cannot combine action and text"):
        _ = ui_action_from_message(
            Message(
                message_id="m-3",
                role=Role.ROLE_USER,
                parts=[Part(text="hi"), _action_part(payload)],
            )
        )
    with pytest.raises(ValueError, match="exactly one action Part"):
        _ = ui_action_from_message(
            Message(
                message_id="m-4",
                role=Role.ROLE_USER,
                parts=[
                    _action_part(payload),
                    _action_part(payload),
                ],
            )
        )


def test_redacted_paths_block_writes_into_around_and_above() -> None:
    assert_fields_outside_redacted(["note", "lead.headcount"], ["/secret"])
    with pytest.raises(PermissionError, match="redacted path '/secret'"):
        assert_fields_outside_redacted(["secret"], ["/secret"])
    with pytest.raises(PermissionError, match="redacted path '/lead'"):
        assert_fields_outside_redacted(["lead.headcount"], ["/lead"])
    with pytest.raises(PermissionError, match="redacted path '/lead/headcount'"):
        assert_fields_outside_redacted(["lead"], ["/lead/headcount"])
