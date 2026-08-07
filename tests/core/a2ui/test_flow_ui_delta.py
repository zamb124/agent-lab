from __future__ import annotations

import pytest

from core.models.flow_interface import default_flow_interface_config
from core.state.flow_ui import (
    FlowUIDeleteComponentsCommand,
    FlowUISetDataCommand,
)
from core.state.flow_ui_delta import (
    FlowUIRevisionConflictError,
    apply_flow_ui_commands,
    decode_json_pointer,
    set_json_pointer,
)


def _document():
    return default_flow_interface_config().template.materialize(
        document_id="flow-ui:context-1"
    )


def test_semantic_command_batch_is_atomic_and_increments_revision_once() -> None:
    original = _document()
    result = apply_flow_ui_commands(
        original,
        [
            FlowUISetDataCommand(
                surface_id="main",
                path="/values/message",
                value="hello",
            ),
            FlowUISetDataCommand(
                surface_id="main",
                path="/values/profile/email",
                value="user@linnex.io",
            ),
        ],
        expected_revision=1,
        client_mutation_id="mutation-1",
        allow_system_data=False,
    )

    assert result.changed is True
    assert result.applied_command_count == 2
    assert result.document.revision == 2
    assert result.document.surfaces["main"].data_model.values == {
        "message": "hello",
        "files": [],
        "profile": {"email": "user@linnex.io"},
    }
    assert original.revision == 1
    assert original.surfaces["main"].data_model.values["message"] == ""


def test_invalid_command_rolls_back_complete_batch() -> None:
    original = _document()
    with pytest.raises(ValueError, match="Unknown Flow UI surface"):
        _ = apply_flow_ui_commands(
            original,
            [
                FlowUISetDataCommand(
                    surface_id="main",
                    path="/values/message",
                    value="must-not-commit",
                ),
                FlowUIDeleteComponentsCommand(
                    surface_id="missing",
                    component_ids=["anything"],
                ),
            ],
        )
    assert original.revision == 1
    assert original.surfaces["main"].data_model.values["message"] == ""


def test_occ_duplicate_idempotency_and_system_namespace_protection() -> None:
    document = _document()
    accepted = apply_flow_ui_commands(
        document,
        [FlowUISetDataCommand(surface_id="main", path="/values/message", value="one")],
        expected_revision=1,
        client_mutation_id="mutation-1",
        allow_system_data=False,
    ).document

    duplicate = apply_flow_ui_commands(
        accepted,
        [FlowUISetDataCommand(surface_id="main", path="/values/message", value="two")],
        expected_revision=2,
        client_mutation_id="mutation-1",
        allow_system_data=False,
    )
    assert duplicate.changed is False
    assert duplicate.document.surfaces["main"].data_model.values["message"] == "one"

    with pytest.raises(FlowUIRevisionConflictError):
        _ = apply_flow_ui_commands(accepted, [], expected_revision=1)
    with pytest.raises(ValueError, match="cannot write /system"):
        _ = apply_flow_ui_commands(
            accepted,
            [FlowUISetDataCommand(surface_id="main", path="/system/admin", value=True)],
            allow_system_data=False,
        )


def test_rfc6901_escape_sequences_round_trip() -> None:
    assert decode_json_pointer("/a~1b/c~0d") == ["a/b", "c~d"]
    value = set_json_pointer({}, "/a~1b/c~0d", "ok")
    assert value == {"a/b": {"c~d": "ok"}}
