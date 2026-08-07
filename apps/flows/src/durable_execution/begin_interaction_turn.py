"""Domain command that opens a new A2A Task in an existing durable context."""

from __future__ import annotations

from typing import Final

from core.a2a import A2ARepresentationSnapshot
from core.state import ExecutionState

# Accepted UI document, conversation, files and durable variables survive.
BEGIN_INTERACTION_TURN_PRESERVED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "context_id",
        "user_id",
        "initiator_user_id",
        "session_id",
        "branch_id",
        "flow_config_version",
        "messages",
        "files",
        "variables",
        "user_groups",
        "triggers",
        "scheduled_tasks",
        "prompt_history",
        "llm_context_memory_cursor",
        "reasoning_history",
        "reflection_history",
        "agent_plan",
        "ui_document",
        "ui_template_version",
        "ui_last_synced_at",
        "ui_last_accepted_client_mutation_id",
        "ui_last_accepted_client_mutation_hash",
        "ui_effect_cursor",
        "ui_applied_effect_ids",
        "a2a_representation",
        "breakpoints",
        "handoff_parent_session_id",
        "handoff_depth",
        "handoff_trace_id",
        "handback_return_variables",
    }
)

# Run-scoped execution fields cleared for the new Task.
BEGIN_INTERACTION_TURN_RESET_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "task_id",
        "content",
        "response",
        "result",
        "validation",
        "terminal_task_state",
        "terminal_task_error",
        "current_nodes",
        "join_arrived_preds",
        "interrupt",
        "interrupt_path",
        "hitl_handoff_correlation_id",
        "hitl_streamed_closing_text",
        "node_history",
        "execution_exceptions",
        "tool_results",
        "nested_states",
        "child_workflows",
        "pending_reasoning",
        "breakpoint_hit",
        "breakpoint_state",
        "ui_interaction",
        "ui_conflict",
        "flow_deadline_monotonic",
        "flow_timeout_effective_seconds",
    }
)

_RESET_EMPTY_VALUES: Final[dict[str, object]] = {
    "task_id": "",
    "content": None,
    "response": None,
    "result": None,
    "validation": None,
    "terminal_task_state": None,
    "terminal_task_error": None,
    "current_nodes": [],
    "join_arrived_preds": {},
    "interrupt": None,
    "interrupt_path": [],
    "hitl_handoff_correlation_id": None,
    "hitl_streamed_closing_text": None,
    "node_history": {},
    "execution_exceptions": [],
    "tool_results": {},
    "nested_states": {},
    "child_workflows": {},
    "pending_reasoning": None,
    "breakpoint_hit": None,
    "breakpoint_state": None,
    "ui_interaction": None,
    "ui_conflict": None,
    "flow_deadline_monotonic": None,
    "flow_timeout_effective_seconds": None,
}


def _assert_field_tables() -> None:
    model_fields = set(ExecutionState.model_fields)
    unknown_preserved = BEGIN_INTERACTION_TURN_PRESERVED_FIELDS - model_fields
    if unknown_preserved:
        raise ValueError(
            "BeginInteractionTurn preserved fields missing on ExecutionState: "
            + f"{sorted(unknown_preserved)}"
        )
    unknown_reset = BEGIN_INTERACTION_TURN_RESET_FIELDS - model_fields
    if unknown_reset:
        raise ValueError(
            "BeginInteractionTurn reset fields missing on ExecutionState: "
            + f"{sorted(unknown_reset)}"
        )
    overlap = BEGIN_INTERACTION_TURN_PRESERVED_FIELDS & BEGIN_INTERACTION_TURN_RESET_FIELDS
    if overlap:
        raise ValueError(
            "BeginInteractionTurn preserved/reset overlap: " + f"{sorted(overlap)}"
        )


def begin_interaction_turn(
    state: ExecutionState,
    *,
    task_id: str,
    representation: A2ARepresentationSnapshot | None = None,
) -> ExecutionState:
    """Open a new Task identity while keeping the accepted Flow UI document.

    Past Task projections are not mutated; only the active pointer and
    run-scoped fields on ExecutionState change.
    """
    _assert_field_tables()
    if not task_id.strip():
        raise ValueError("BeginInteractionTurn requires a non-empty task_id")
    if task_id == state.task_id and state.terminal_task_state is None:
        raise ValueError(
            "BeginInteractionTurn requires a new task_id when the current Task "
            + "is still non-terminal"
        )

    next_state = state.model_copy(deep=True)
    for field_name, empty_value in _RESET_EMPTY_VALUES.items():
        if field_name == "task_id":
            setattr(next_state, field_name, task_id)
            continue
        setattr(next_state, field_name, empty_value)
    if representation is not None:
        next_state.a2a_representation = representation
    return next_state


__all__ = [
    "BEGIN_INTERACTION_TURN_PRESERVED_FIELDS",
    "BEGIN_INTERACTION_TURN_RESET_FIELDS",
    "begin_interaction_turn",
]
