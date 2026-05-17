"""
Защита системных полей ExecutionState от user code/runtime merge.
"""

from __future__ import annotations

import pytest

from apps.flows.src.runtime.nodes import BaseNode
from apps.flows.src.runtime_helpers.state_utils import merge_state, set_nested
from core.errors import FrozenStateFieldError
from core.state import ExecutionState
from core.state.mutation_policy import (
    FROZEN_STATE_FIELDS,
    USER_TOOL_PARALLEL_STATE_MERGE_FIELDS,
    assert_frozen_fields_unchanged,
    snapshot_frozen_fields,
    user_code_state_mutation_guard,
)


def _minimal_state() -> ExecutionState:
    return ExecutionState.create(
        task_id="task_1",
        context_id="ctx_1",
        user_id="user_1",
        session_id="flow_a:ctx_1",
        content="hi",
    )


def test_user_guard_blocks_frozen_setattr() -> None:
    state = _minimal_state()
    with user_code_state_mutation_guard():
        with pytest.raises(FrozenStateFieldError) as exc:
            state.task_id = "other"
        assert exc.value.payload["field"] == "task_id"


def test_runtime_allows_frozen_setattr() -> None:
    state = _minimal_state()
    state.task_id = "task_2"
    assert state.task_id == "task_2"


def test_merge_state_rejects_frozen_key_on_execution_state() -> None:
    state = _minimal_state()
    with pytest.raises(FrozenStateFieldError):
        merge_state(state, {"flow_deadline_monotonic": 999.0})


def test_set_nested_rejects_frozen_root() -> None:
    state = _minimal_state()
    with pytest.raises(FrozenStateFieldError):
        set_nested(state, "node_history.x", {})


def test_snapshot_detects_in_place_mutation() -> None:
    state = _minimal_state()
    state.node_history["n1"] = {"calls": []}
    snap = snapshot_frozen_fields(state)
    state.node_history["n1"]["calls"].append({"x": 1})
    with pytest.raises(FrozenStateFieldError) as exc:
        assert_frozen_fields_unchanged(state, snap)
    assert exc.value.payload["reason"] == "in_place_mutation"


class _DummyNode(BaseNode):
    async def _run_impl(self, state: ExecutionState, inputs: dict) -> object:
        return None


def test_apply_output_mapping_rejects_frozen_key() -> None:
    node = _DummyNode("n1")
    state = _minimal_state()
    with pytest.raises(FrozenStateFieldError):
        node._apply_output_mapping(state, {"session_id": "x:y"})


def test_copy_state_back_preserves_target_identity_when_not_full_trust() -> None:
    node = _DummyNode("n1")
    tgt = _minimal_state()
    src_dict = tgt.model_dump(exclude_none=False)
    src_dict["task_id"] = "forged"
    src_dict["variables"] = {"k": 1}
    src = ExecutionState.model_validate(src_dict)
    node._copy_state_back(src, tgt, full_trust=False)
    assert tgt.task_id == "task_1"
    assert tgt.variables == {"k": 1}


def test_parallel_merge_allowlist_excludes_identity() -> None:
    assert "task_id" not in USER_TOOL_PARALLEL_STATE_MERGE_FIELDS
    assert "flow_deadline_monotonic" not in USER_TOOL_PARALLEL_STATE_MERGE_FIELDS
    assert "variables" in USER_TOOL_PARALLEL_STATE_MERGE_FIELDS


def test_messages_not_in_frozen_set() -> None:
    assert "messages" not in FROZEN_STATE_FIELDS
