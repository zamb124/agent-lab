"""Table-driven BeginInteractionTurn preserved/reset field contract."""

from __future__ import annotations

from apps.flows.src.durable_execution import (
    BEGIN_INTERACTION_TURN_PRESERVED_FIELDS,
    BEGIN_INTERACTION_TURN_RESET_FIELDS,
    begin_interaction_turn,
)
from core.models.flow_interface import default_flow_interface_config
from core.state import ExecutionState


def _state(**overrides: object) -> ExecutionState:
    document = default_flow_interface_config().template.materialize(
        document_id="flow-ui:ctx-1"
    )
    data: dict[str, object] = {
        "task_id": "task-old",
        "context_id": "ctx-1",
        "user_id": "user-1",
        "session_id": "flow-1:ctx-1",
        "branch_id": "default",
        "content": "previous content",
        "response": "previous response",
        "result": {"done": True},
        "terminal_task_state": "completed",
        "terminal_task_error": None,
        "current_nodes": ["llm"],
        "messages": [],
        "variables": {"kept": 1},
        "files": [],
        "tool_results": {"t1": {"ok": True}},
        "prompt_history": [],
        "reasoning_history": [{"text": "why"}],
        "reflection_history": [],
        "ui_document": document,
        "ui_template_version": document.template_version,
        "ui_applied_effect_ids": ["effect-1"],
        "ui_effect_cursor": 3,
    }
    data.update(overrides)
    return ExecutionState.model_validate(data)


def test_begin_interaction_turn_field_tables_are_disjoint_and_complete() -> None:
    model_fields = set(ExecutionState.model_fields)
    assert BEGIN_INTERACTION_TURN_PRESERVED_FIELDS <= model_fields
    assert BEGIN_INTERACTION_TURN_RESET_FIELDS <= model_fields
    assert not (
        BEGIN_INTERACTION_TURN_PRESERVED_FIELDS & BEGIN_INTERACTION_TURN_RESET_FIELDS
    )


def test_begin_interaction_turn_preserves_ui_and_clears_run_scoped_fields() -> None:
    before = _state()
    after = begin_interaction_turn(before, task_id="task-new")

    before_dump = before.model_dump(mode="json", exclude_none=False)
    after_dump = after.model_dump(mode="json", exclude_none=False)

    for field_name in sorted(BEGIN_INTERACTION_TURN_PRESERVED_FIELDS):
        assert after_dump[field_name] == before_dump[field_name], field_name

    assert after.task_id == "task-new"
    assert after.terminal_task_state is None
    assert after.terminal_task_error is None
    assert after.content is None
    assert after.response is None
    assert after.result is None
    assert after.current_nodes == []
    assert after.tool_results == {}
    assert after.ui_interaction is None
    assert after.ui_document == before.ui_document
    assert after.ui_applied_effect_ids == ["effect-1"]
    assert after.messages == before.messages
    assert after.variables == before.variables
