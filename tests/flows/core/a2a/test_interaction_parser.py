from __future__ import annotations

import pytest
from a2a.types import Message, Part, Role

from apps.flows.src.a2a.interaction_parser import (
    FlowUIIngressKind,
    parse_flow_ui_command,
)
from core.a2a import (
    A2UI_EXTENSION_URI,
    A2UI_PLATFORM_CATALOG_ID,
    PLATFORM_UI_SUBMIT_ACTION,
    struct_from_mapping,
)
from core.a2ui import A2UI091Codec


def _submit_message(*, extension: bool = True) -> Message:
    part = A2UI091Codec().encode_data_part(
        [
            {
                "version": "v0.9.1",
                "action": {
                    "name": PLATFORM_UI_SUBMIT_ACTION,
                    "surfaceId": "main",
                    "sourceComponentId": "submit",
                    "timestamp": "2026-08-04T12:00:00Z",
                    "context": {"formId": "message-form"},
                },
            }
        ]
    )
    return Message(
        message_id="message-1",
        context_id="context-1",
        role=Role.ROLE_USER,
        parts=[part],
        extensions=[A2UI_EXTENSION_URI] if extension else [],
        metadata=struct_from_mapping(
            {
                "a2uiClientCapabilities": {
                    "v0.9.1": {
                        "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                        "inlineCatalogs": [],
                    }
                },
                "a2uiClientDataModel": {
                    "version": "v0.9.1",
                    "surfaces": {
                        "main": {
                            "content": {"forged": True},
                            "values": {"message": "Hello"},
                            "system": {"forged": True},
                        }
                    },
                },
                "platformUi": {
                    "documentId": "flow-ui:context-1",
                    "revision": 4,
                    "actionId": "action-1",
                    "clientMutationId": "mutation-1",
                    "activePageId": "main",
                    "sessionViewState": {"mainTab": "result"},
                },
            }
        ),
    )


def test_ordinary_a2a_message_does_not_enter_flow_ui_ingress() -> None:
    message = Message(
        message_id="ordinary",
        role=Role.ROLE_USER,
        parts=[Part(text="ordinary A2A remains ordinary")],
    )
    assert parse_flow_ui_command(message) is None


def test_submit_is_decoded_from_one_standard_a2a_data_part() -> None:
    command = parse_flow_ui_command(_submit_message())
    assert command is not None
    assert command.kind == FlowUIIngressKind.SUBMIT
    assert command.document_id == "flow-ui:context-1"
    assert command.base_revision == 4
    assert command.action_id == "action-1"
    assert command.client_mutation_id == "mutation-1"
    assert command.decoded.data_model is not None
    assert command.decoded.data_model.surfaces["main"]["values"] == {
        "message": "Hello"
    }
    assert command.original_message["extensions"] == [A2UI_EXTENSION_URI]


def test_a2ui_payload_without_message_extension_fails_closed() -> None:
    with pytest.raises(ValueError, match="extension URI"):
        _ = parse_flow_ui_command(_submit_message(extension=False))


def test_platform_ui_metadata_rejects_unknown_fields() -> None:
    message = _submit_message()
    metadata = {
        "a2uiClientCapabilities": {
            "v0.9.1": {
                "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                "inlineCatalogs": [],
            }
        },
        "a2uiClientDataModel": {
            "version": "v0.9.1",
            "surfaces": {"main": {"values": {"message": "Hello"}}},
        },
        "platformUi": {
            "documentId": "flow-ui:context-1",
            "revision": 1,
            "actionId": "action-1",
            "unexpected": True,
        },
    }
    message.metadata.CopyFrom(struct_from_mapping(metadata))
    with pytest.raises(ValueError, match="unknown fields"):
        _ = parse_flow_ui_command(message)
