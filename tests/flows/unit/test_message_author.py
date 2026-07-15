"""Strict author provenance contract for shared chat messages."""

import pytest
from pydantic import ValidationError

from apps.flows.src.runtime.message_author import (
    FlowMessageAuthor,
    build_flow_message_author,
)
from apps.flows.src.streaming import InMemoryEmitter
from core.state import ExecutionState

pytestmark = [pytest.mark.no_test_doubles]


def _state(*, flow_id: str, handoff_depth: int) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-{flow_id}",
        context_id=f"context-{flow_id}",
        user_id="user-1",
        session_id=f"{flow_id}:context-{flow_id}",
        handoff_depth=handoff_depth,
    )


def test_parent_flow_message_has_typed_agent_author() -> None:
    author = build_flow_message_author(
        _state(flow_id="support_agent", handoff_depth=0),
        node_id="answer",
    )

    assert author == {
        "kind": "agent",
        "flow_id": "support_agent",
        "node_id": "answer",
        "name": "",
    }


def test_handoff_child_message_has_typed_subagent_author() -> None:
    author = build_flow_message_author(
        _state(flow_id="returns_agent", handoff_depth=1),
        node_id="resolve_return",
    )

    assert author == {
        "kind": "subagent",
        "flow_id": "returns_agent",
        "node_id": "resolve_return",
        "name": "",
    }


@pytest.mark.asyncio
async def test_production_in_memory_emitter_preserves_subagent_author_on_chunks_and_terminal() -> None:
    emitter = InMemoryEmitter(_state(flow_id="returns_agent", handoff_depth=1))

    await emitter.emit_text("Возврат оформлен")
    await emitter.emit_complete("Готово")

    chunk, terminal = emitter.events
    assert chunk.artifact.metadata == {
        "author": {
            "kind": "subagent",
            "flow_id": "returns_agent",
            "name": "",
        }
    }
    assert terminal.status.message is not None
    assert terminal.status.message.metadata == chunk.artifact.metadata


@pytest.mark.parametrize(
    ("overrides", "error_fragment"),
    [
        ({"kind": "unknown"}, "kind"),
        ({"flow_id": ""}, "flow_id"),
        ({"node_id": ""}, "node_id"),
        ({"extra": True}, "Extra inputs are not permitted"),
    ],
)
def test_author_contract_rejects_invalid_payloads(
    overrides: dict[str, object],
    error_fragment: str,
) -> None:
    payload: dict[str, object] = {
        "kind": "agent",
        "flow_id": "support_agent",
        "node_id": "answer",
    }
    payload.update(overrides)

    with pytest.raises(ValidationError, match=error_fragment):
        FlowMessageAuthor.model_validate(payload)
