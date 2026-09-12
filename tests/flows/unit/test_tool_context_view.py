"""Unit tests for allowlisted ExecutionState projection for code runners."""

from __future__ import annotations

from apps.flows.src.runners.tool_context_view import build_tool_context_view
from core.state import ExecutionState


def test_tool_context_view_includes_user_extras() -> None:
    state = ExecutionState.model_validate(
        {
            "task_id": "task-1",
            "context_id": "ctx-1",
            "user_id": "user-1",
            "session_id": "flow:ctx-1",
            "tool_ids": {"python": "cap_python"},
            "secret": "my-secret",
        }
    )
    view = build_tool_context_view(state)
    assert view["tool_ids"] == {"python": "cap_python"}
    assert view["secret"] == "my-secret"
    assert view["messages"] == []
    assert view["tool_results"] == {}
    assert view["ui_slots"] == {}
    assert "flow_timeout_effective_seconds" not in view
    assert "flow_deadline_monotonic" not in view
    assert "node_history" not in view
