"""Semantic UI fields on ExecutionStateDelta round-trip."""

from __future__ import annotations

from apps.flows.src.durable_execution import apply_state_delta, build_state_delta
from core.models.flow_interface import default_flow_interface_config
from core.state import ExecutionState
from core.state.flow_ui import FlowUISetDataCommand
from core.state.flow_ui_delta import apply_flow_ui_commands


def _state(**overrides: object) -> ExecutionState:
    document = default_flow_interface_config().template.materialize(
        document_id="flow-ui:ctx-1"
    )
    data: dict[str, object] = {
        "task_id": "task-1",
        "context_id": "ctx-1",
        "user_id": "user-1",
        "session_id": "flow-1:ctx-1",
        "branch_id": "default",
        "content": "hello",
        "ui_document": document,
        "ui_template_version": document.template_version,
    }
    data.update(overrides)
    return ExecutionState.model_validate(data)


def test_ui_document_change_uses_semantic_fields_not_whole_document() -> None:
    before = _state()
    after = before.model_copy(deep=True)
    patched = apply_flow_ui_commands(
        after.ui_document,
        [
            FlowUISetDataCommand(
                surface_id="main",
                path="/values",
                value={"message": "draft", "files": []},
            )
        ],
        expected_revision=1,
        client_mutation_id="mut-1",
    ).document
    after.ui_document = patched
    after.ui_last_accepted_client_mutation_id = "mut-1"
    after.ui_template_version = patched.template_version

    delta = build_state_delta(before, after)
    assert "ui_document" not in delta.fields_set
    assert delta.ui_revision_set == 2
    assert delta.ui_data_set
    assert delta.ui_last_client_mutation_set is not None
    assert delta.ui_last_client_mutation_set.mutation_id == "mut-1"

    restored = apply_state_delta(before, delta)
    assert restored.ui_document == after.ui_document
    assert restored.ui_last_accepted_client_mutation_id == "mut-1"
