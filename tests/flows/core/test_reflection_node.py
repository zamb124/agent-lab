"""Durable ReflectionNode tests: real container + MockLLM only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.nodes import ReflectionNode, create_node
from core.clients.llm.mock import MockLLM
from core.reflection import CriticSeverity, ReflectionTargetKind
from core.state import ExecutionState
from core.types import JsonObject
from tests.flows.durable_runtime_harness import ensure_workflow_started, run_node, workflow_state
from tests.flows.fixtures.reflection import (
    critique_issue,
    mock_critique_queue_item,
    reflection_critique,
    reflection_node_config,
    reflection_policy,
)

MockLLMQueue = Callable[[list[Any]], MockLLM]
MockLLMCapture = Callable[[], Awaitable[list[JsonObject]]]


async def _reflection_node(
    container: FlowRuntimeContainer,
    *,
    config: JsonObject | None = None,
) -> ReflectionNode:
    node = await create_node(
        "critic",
        config or reflection_node_config(),
        container=container,
    )
    assert isinstance(node, ReflectionNode)
    return node


@pytest.mark.asyncio
async def test_reflection_blocks_and_records_typed_result(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-block-{unique_id}"
    critique = reflection_critique(
        decision="blocked",
        confidence=0.98,
        summary="Destructive production action without approval.",
        issues=[critique_issue()],
    )
    mock_llm_with_queue([mock_critique_queue_item(critique)])
    node = await _reflection_node(container)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Run destructive migration on production without approval.",
    )

    out = await run_node(container=container, node=node, state=state)

    assert out.response == "Run destructive migration on production without approval."
    assert out.validation is not None
    assert out.validation["approved"] is False
    assert out.validation["gate"] == "final_answer"
    assert out.validation["critique"]["decision"] == "blocked"
    assert out.reflection_history[0].result.approved is False
    assert out.reflection_history[0].node_id == "critic"
    assert "issue:critical:safety" in out.validation["blocked_reasons"]
    assert len(out.ui_events_pending) == 1
    ui_event = out.ui_events_pending[0]
    assert ui_event.event_type == "platform.reflection_resolved"
    assert ui_event.payload["exit_id"] == "blocked"
    assert ui_event.payload["approved"] is False
    assert ui_event.payload["decision"] == "blocked"
    assert ui_event.payload["exit_label"] == "Blocked"


@pytest.mark.asyncio
async def test_reflection_approves_clean_critique(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-ok-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(container)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Safe staged migration plan.",
    )

    out = await run_node(container=container, node=node, state=state)

    assert out.validation is not None
    assert out.validation["approved"] is True
    assert out.validation["blocked_reasons"] == []
    assert out.reflection_history[0].result.approved is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_kind", "state_path", "extra_state"),
    [
        ("response", None, {"response": "Answer text"}),
        ("result", None, {"result": {"ok": True}}),
        ("validation", None, {"validation": {"prior": True}}),
        ("state_path", "variables.draft", {"variables": {"draft": "draft body"}}),
    ],
)
async def test_reflection_resolves_targets(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    target_kind: ReflectionTargetKind,
    state_path: str | None,
    extra_state: dict[str, object],
) -> None:
    flow_id = f"refl-tgt-{target_kind}-{unique_id}"
    policy = reflection_policy(target_kind=target_kind, state_path=state_path)
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(
        container,
        config=reflection_node_config(policy=policy),
    )
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, **extra_state)

    out = await run_node(container=container, node=node, state=state)

    assert out.validation is not None
    assert out.validation["approved"] is True
    assert out.validation["target"]["kind"] == target_kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [None, "", "   "],
)
async def test_reflection_rejects_empty_response_target(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    response: str | None,
) -> None:
    flow_id = f"refl-empty-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(container)
    if response is None:
        state = workflow_state(flow_id=flow_id, unique_id=unique_id)
    else:
        state = workflow_state(flow_id=flow_id, unique_id=unique_id, response=response)

    with pytest.raises(ValueError, match="empty"):
        await run_node(container=container, node=node, state=state)


@pytest.mark.asyncio
async def test_reflection_activity_replays_without_second_llm_call(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture: MockLLMCapture,
) -> None:
    flow_id = f"refl-replay-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(container)
    first_state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Use staged migration.",
    )
    first = await run_node(container=container, node=node, state=first_state)
    record = first.reflection_history[0]

    replay_state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Use staged migration.",
    )
    replay_state = ExecutionState.model_validate(
        {
            **replay_state.model_dump(mode="python"),
            "session_id": first.session_id,
            "task_id": first.task_id,
            "context_id": first.context_id,
        }
    )
    await ensure_workflow_started(
        container=container,
        state=replay_state,
        flow_id=flow_id,
        branch_id=replay_state.branch_id,
    )
    replay_state.attach_durable_node_context(
        execution_branch_id=record.execution_branch_id,
        node_schedule_sequence=record.node_schedule_sequence,
        superstep_sequence=0,
    )
    second = await node.run(replay_state)

    assert first.validation == second.validation
    assert first.reflection_history[0].result == second.reflection_history[0].result
    calls = await mock_llm_capture()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_reflection_requires_durable_workflow_context(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(container)
    state = workflow_state(
        flow_id=f"refl-nodurable-{unique_id}",
        unique_id=unique_id,
        response="x",
    )
    with pytest.raises(RuntimeError, match="durable"):
        await node.run(state)


@pytest.mark.asyncio
@pytest.mark.parametrize("severity", ["error", "critical"])
async def test_reflection_blocks_on_configured_severity(
    container: FlowRuntimeContainer,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    severity: CriticSeverity,
) -> None:
    flow_id = f"refl-sev-{severity}-{unique_id}"
    policy = reflection_policy(block_on_severities=[severity])
    critique = reflection_critique(
        issues=[critique_issue(criterion_id="c1", severity=severity)],
    )
    mock_llm_with_queue([mock_critique_queue_item(critique)])
    node = await _reflection_node(
        container,
        config=reflection_node_config(policy=policy),
    )
    out = await run_node(
        container=container,
        node=node,
        state=workflow_state(
            flow_id=flow_id,
            unique_id=unique_id,
            response="Safe staged migration plan.",
        ),
    )
    assert out.validation is not None
    assert out.validation["approved"] is False
    assert f"issue:{severity}:c1" in out.validation["blocked_reasons"]
