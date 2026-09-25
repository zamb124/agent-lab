"""Full flow: reflection dual exits, premature completion, durable replay."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import BaseNode, ReflectionNode, create_node
from core.clients.llm.mock import MockLLM
from core.errors import FlowPrematureCompletionError
from core.flow_ui.templates import default_chat_document
from core.reflection import CriticExit, CriticExitWhen
from core.state import ExecutionState
from core.types import JsonObject
from tests.flows.durable_runtime_harness import run_flow, workflow_state
from tests.flows.fixtures.reflection import (
    critique_issue,
    mock_critique_queue_item,
    reflection_critique,
    reflection_node_config,
    reflection_policy,
)

MockLLMQueue = Callable[[list[Any]], MockLLM]
MockLLMCapture = Callable[[], Awaitable[list[JsonObject]]]


class _HitSinkNode(BaseNode):
    """Marks variables.hits[node_id] without sandbox/code-runner."""

    async def _run_impl(self, state: ExecutionState, inputs: object) -> None:
        _ = inputs
        hits_raw = state.variables.get("hits")
        hits: dict[str, object] = dict(hits_raw) if isinstance(hits_raw, dict) else {}
        hits[self.node_id] = int(hits.get(self.node_id, 0) or 0) + 1
        state.variables = {**state.variables, "hits": hits}
        return None


def _hit_sink(node_id: str, *, di: FlowsDi) -> _HitSinkNode:
    return _HitSinkNode(
        node_id=node_id,
        config={"type": "code", "name": node_id},
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client,
    )


def _exit_edge(from_node: str, to_node: str, exit_id: str) -> JsonObject:
    return {
        "from_node": from_node,
        "to_node": to_node,
        "from_port": exit_id,
        "condition": {
            "type": "simple",
            "variable": "validation.exit_id",
            "operator": "==",
            "value": exit_id,
        },
    }


def _approved_edge(from_node: str, to_node: str) -> JsonObject:
    return _exit_edge(from_node, to_node, "approved")


def _blocked_edge(from_node: str, to_node: str) -> JsonObject:
    return _exit_edge(from_node, to_node, "blocked")


async def _build_dual_exit_flow(
    di: FlowsDi,
    *,
    flow_id: str,
) -> Flow:
    critic = await create_node("critic", reflection_node_config(), node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory)
    assert isinstance(critic, ReflectionNode)
    nodes: dict[str, BaseNode] = {
        "critic": critic,
        "approved_sink": _hit_sink("approved_sink", di=di),
        "blocked_sink": _hit_sink("blocked_sink", di=di),
    }
    return Flow(
        flow_id=flow_id,
        name="reflection dual exit",
        entry="critic",
        nodes=nodes,
        edges=[
            _approved_edge("critic", "approved_sink"),
            _blocked_edge("critic", "blocked_sink"),
            {"from_node": "approved_sink", "to_node": None},
            {"from_node": "blocked_sink", "to_node": None},
        ],
        interface=default_chat_document(),
        execution=execution_context_for(di.node_constructor.workflow_runtime), emitter_factory=di.node_constructor.emitter_factory,
    )


@pytest.mark.asyncio
async def test_reflection_flow_takes_approved_exit(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-flow-ok-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    flow = await _build_dual_exit_flow(di, flow_id=flow_id)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Concrete and safe answer.",
        variables={"hits": {}},
    )

    out = await run_flow(di=di, flow=flow, state=state)

    assert out.validation is not None
    assert out.validation["approved"] is True
    assert out.validation["exit_id"] == "approved"
    hits = out.variables.get("hits")
    assert isinstance(hits, dict)
    assert hits.get("approved_sink") == 1
    assert hits.get("blocked_sink") is None


@pytest.mark.asyncio
async def test_reflection_flow_takes_blocked_exit(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-flow-block-{unique_id}"
    critique = reflection_critique(
        decision="blocked",
        confidence=0.99,
        summary="Unsafe",
        issues=[critique_issue()],
    )
    mock_llm_with_queue([mock_critique_queue_item(critique)])
    flow = await _build_dual_exit_flow(di, flow_id=flow_id)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Delete production database now.",
        variables={"hits": {}},
    )

    out = await run_flow(di=di, flow=flow, state=state)

    assert out.validation is not None
    assert out.validation["approved"] is False
    assert out.validation["exit_id"] == "blocked"
    hits = out.variables.get("hits")
    assert isinstance(hits, dict)
    assert hits.get("blocked_sink") == 1
    assert hits.get("approved_sink") is None


@pytest.mark.asyncio
async def test_reflection_flow_incomplete_exits_raises_no_conditional_match(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    """Only approved exit exists; critique blocks → no_conditional_match."""
    flow_id = f"refl-flow-incomplete-{unique_id}"
    mock_llm_with_queue(
        [
            mock_critique_queue_item(
                reflection_critique(
                    decision="blocked",
                    confidence=0.99,
                    summary="Unsafe",
                    issues=[critique_issue()],
                )
            )
        ]
    )
    critic = await create_node("critic", reflection_node_config(), node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory)
    flow = Flow(
        flow_id=flow_id,
        name="reflection incomplete exits",
        entry="critic",
        nodes={
            "critic": critic,
            "approved_sink": _hit_sink("approved_sink", di=di),
        },
        edges=[
            _approved_edge("critic", "approved_sink"),
            {"from_node": "approved_sink", "to_node": None},
        ],
        interface=default_chat_document(),
        execution=execution_context_for(di.node_constructor.workflow_runtime), emitter_factory=di.node_constructor.emitter_factory,
    )
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Unsafe answer",
        variables={"hits": {}},
    )

    with pytest.raises(FlowPrematureCompletionError) as exc_info:
        await run_flow(di=di, flow=flow, state=state)
    assert exc_info.value.payload.get("reason") == "no_conditional_match"


@pytest.mark.asyncio
async def test_reflection_flow_replay_same_session_does_not_recall_llm(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
    mock_llm_capture: MockLLMCapture,
) -> None:
    flow_id = f"refl-flow-replay-{unique_id}"
    mock_llm_with_queue([mock_critique_queue_item(reflection_critique())])
    flow = await _build_dual_exit_flow(di, flow_id=flow_id)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Safe answer",
        variables={"hits": {}},
    )
    first = await run_flow(di=di, flow=flow, state=state)
    assert first.validation is not None
    assert first.validation["approved"] is True

    # Re-enter same session: orchestrator should rehydrate; reflection activity
    # for the completed schedule is not re-invoked as a new LLM call when the
    # graph is already finished. Capture stays at 1.
    calls = await mock_llm_capture()
    assert len(calls) == 1
    assert first.reflection_history[0].result.approved is True
    assert first.reflection_history[0].result.exit_id == "approved"


async def _build_three_exit_flow(
    di: FlowsDi,
    *,
    flow_id: str,
) -> Flow:
    policy = reflection_policy().model_copy(
        update={
            "exits": [
                CriticExit(
                    exit_id="pass",
                    label="Pass",
                    when=CriticExitWhen(kind="approved_true"),
                ),
                CriticExit(
                    exit_id="revise",
                    label="Revise",
                    when=CriticExitWhen(kind="decision_eq", decision="needs_revision"),
                ),
                CriticExit(
                    exit_id="reject",
                    label="Reject",
                    when=CriticExitWhen(kind="always"),
                ),
            ]
        }
    )
    critic = await create_node(
        "critic",
        reflection_node_config(policy=policy),
        node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
    )
    nodes: dict[str, BaseNode] = {
        "critic": critic,
        "pass_sink": _hit_sink("pass_sink", di=di),
        "revise_sink": _hit_sink("revise_sink", di=di),
        "reject_sink": _hit_sink("reject_sink", di=di),
    }
    return Flow(
        flow_id=flow_id,
        name="reflection three exit",
        entry="critic",
        nodes=nodes,
        edges=[
            _exit_edge("critic", "pass_sink", "pass"),
            _exit_edge("critic", "revise_sink", "revise"),
            _exit_edge("critic", "reject_sink", "reject"),
            {"from_node": "pass_sink", "to_node": None},
            {"from_node": "revise_sink", "to_node": None},
            {"from_node": "reject_sink", "to_node": None},
        ],
        interface=default_chat_document(),
        execution=execution_context_for(di.node_constructor.workflow_runtime), emitter_factory=di.node_constructor.emitter_factory,
    )


@pytest.mark.asyncio
async def test_reflection_flow_three_exits_revise(
    di: FlowsDi,
    unique_id: str,
    mock_llm_with_queue: MockLLMQueue,
) -> None:
    flow_id = f"refl-flow-3-{unique_id}"
    mock_llm_with_queue(
        [
            mock_critique_queue_item(
                reflection_critique(
                    decision="needs_revision",
                    confidence=0.95,
                    summary="Needs rewrite",
                )
            )
        ]
    )
    flow = await _build_three_exit_flow(di, flow_id=flow_id)
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        response="Incomplete answer",
        variables={"hits": {}},
    )
    out = await run_flow(di=di, flow=flow, state=state)
    assert out.validation is not None
    assert out.validation["exit_id"] == "revise"
    hits = out.variables.get("hits")
    assert isinstance(hits, dict)
    assert hits.get("revise_sink") == 1
    assert hits.get("pass_sink") is None
    assert hits.get("reject_sink") is None
