"""Durable ReflectionNode tests: real di + MockLLM only."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.reflection import CriticSeverity, ReflectionTargetKind
from apps.flows.src.runtime.nodes import ReflectionNode, create_node
from apps.flows.src.state import ExecutionState
from core.clients.llm.mock import MockLLM
from core.ui_document.document import FlowUIReflection
from core.ui_document.protocol import CONVERSATION_SLOT_ID, FlowUIRender
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
    di: FlowsDi,
    *,
    config: JsonObject | None = None,
) -> ReflectionNode:
    node = await create_node(
        "critic",
        config or reflection_node_config(),
        node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
    )
    assert isinstance(node, ReflectionNode)
    return node


@pytest.mark.asyncio
async def test_reflection_blocks_and_records_typed_result(
    di: FlowsDi,
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
    node = await _reflection_node(di)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Run destructive migration on production without approval.",
    )

    out = await run_node(di=di, node=node, state=state)

    assert out.response == "Run destructive migration on production without approval."
    assert out.validation is not None
    assert out.validation["approved"] is False
    assert out.validation["gate"] == "final_answer"
    assert out.validation["critique"]["decision"] == "blocked"
    assert out.reflection_history[0].result.approved is False
    assert out.reflection_history[0].node_id == "critic"
    assert "issue:critical:safety" in out.validation["blocked_reasons"]
    events = out.drain_ui_events()
    assert len(events) == 1
    render = events[0]
    assert isinstance(render, FlowUIRender)
    assert render.slot_id == CONVERSATION_SLOT_ID
    card = render.blocks[0]
    assert isinstance(card, FlowUIReflection)
    assert card.block_id == "reflection-critic-blocked"
    assert card.text.startswith("**Blocked** — blocked")
    assert "issue:critical:safety" in card.text


@pytest.mark.asyncio
async def test_reflection_approves_clean_critique(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-ok-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(di)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Safe staged migration plan.",
    )

    out = await run_node(di=di, node=node, state=state)

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
    di: FlowsDi,
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
        di,
        config=reflection_node_config(policy=policy),
    )
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, **extra_state)

    out = await run_node(di=di, node=node, state=state)

    assert out.validation is not None
    assert out.validation["approved"] is True
    assert out.validation["target"]["kind"] == target_kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [None, "", "   "],
)
async def test_reflection_rejects_empty_response_target(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    response: str | None,
) -> None:
    flow_id = f"refl-empty-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(di)
    if response is None:
        state = workflow_state(flow_id=flow_id, unique_id=unique_id)
    else:
        state = workflow_state(flow_id=flow_id, unique_id=unique_id, response=response)

    with pytest.raises(ValueError, match="empty"):
        await run_node(di=di, node=node, state=state)


@pytest.mark.asyncio
async def test_reflection_activity_replays_without_second_llm_call(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture: MockLLMCapture,
) -> None:
    flow_id = f"refl-replay-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(di)
    first_state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Use staged migration.",
    )
    first = await run_node(di=di, node=node, state=first_state)
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
        di=di,
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
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    node = await _reflection_node(di)
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
    di: FlowsDi,
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
        di,
        config=reflection_node_config(policy=policy),
    )
    out = await run_node(
        di=di,
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
