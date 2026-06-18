from __future__ import annotations

from copy import deepcopy

from apps.flows.src.runners.remote import (
    _frozen_fields_differ,
    _merge_returned_state_fields,
    _restore_frozen_fields_from_snapshot,
)
from core.state import ExecutionState
from core.state.mutation_policy import snapshot_frozen_fields


def _minimal_state() -> ExecutionState:
    return ExecutionState.create(
        task_id="task_1",
        context_id="ctx_1",
        user_id="user_1",
        session_id="public_search:ctx_1",
        content="query",
    )


def test_merge_returned_state_fields_ignores_node_history_echo() -> None:
    state = _minimal_state()
    state.node_history["search_answer"] = {
        "type": "llm_node",
        "calls": [{"response": "answer"}],
    }
    state["search_user_query"] = "gamemarkt"
    frozen_snapshot = snapshot_frozen_fields(state)

    returned_payload = state.model_dump(mode="json", exclude_none=False)
    returned_payload["node_history"] = {
        **returned_payload["node_history"],
        "build_search_artifact": {"type": "code", "calls": []},
    }
    returned_payload["search_markdown_sources"] = "1. [Example](https://example.com)"
    returned_state = ExecutionState.model_validate(returned_payload)

    assert _frozen_fields_differ(returned_state, frozen_snapshot) == ["node_history"]
    _restore_frozen_fields_from_snapshot(returned_state, frozen_snapshot)
    assert _frozen_fields_differ(returned_state, frozen_snapshot) == []

    before_history = deepcopy(state.node_history)
    _merge_returned_state_fields(state, returned_state)
    assert state.node_history == before_history
    assert state["search_markdown_sources"] == "1. [Example](https://example.com)"
