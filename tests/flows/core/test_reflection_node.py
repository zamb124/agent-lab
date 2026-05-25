from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

import apps.flows.src.runtime.nodes as runtime_nodes
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import SideEffectPolicy
from apps.flows.src.models import NodeConfig, NodeLLMConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import ReflectionNode, create_node
from core.reflection import (
    CriticCriterion,
    CriticPolicy,
    ReflectionCritiqueIssue,
    ReflectionCritiqueResult,
    ReflectionTarget,
)
from core.state import ExecutionState
from core.types import JsonObject


class RecordingWorkflowRuntime:
    def __init__(self) -> None:
        self.completed_result: JsonObject | None = None
        self.scheduled: list[JsonObject] = []
        self.started: list[str] = []
        self.completed: list[JsonObject] = []

    async def get_active_execution_position(self, session_id: str) -> SimpleNamespace:
        _ = session_id
        return SimpleNamespace(execution_branch_id="branch-1")

    async def record_activity_scheduled(
        self,
        *,
        session_id: str,
        activity_id: str,
        activity_type: str,
        input_payload: JsonObject,
        node_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
        side_effect_policy: SideEffectPolicy,
    ) -> JsonObject | None:
        self.scheduled.append(
            {
                "session_id": session_id,
                "activity_id": activity_id,
                "activity_type": activity_type,
                "input_payload": input_payload,
                "node_id": node_id,
                "tool_call_id": tool_call_id,
                "idempotency_key": idempotency_key,
                "side_effect_policy": side_effect_policy.value,
            }
        )
        return self.completed_result

    async def record_activity_started(self, *, activity_id: str) -> bool:
        self.started.append(activity_id)
        return True

    async def record_activity_completed(
        self,
        *,
        activity_id: str,
        result_json: JsonObject | None = None,
        error: str | None = None,
    ) -> bool:
        self.completed.append(
            {
                "activity_id": activity_id,
                "result_json": result_json,
                "error": error,
            }
        )
        if result_json is not None:
            self.completed_result = result_json
        return True


class NoWorkflowRuntime(RecordingWorkflowRuntime):
    async def get_active_execution_position(self, session_id: str) -> None:
        _ = session_id
        return None


class RuntimeContainer:
    def __init__(self, workflow_runtime: RecordingWorkflowRuntime) -> None:
        self.workflow_runtime = workflow_runtime


class FakeCriticLLM:
    def __init__(self, critique: ReflectionCritiqueResult) -> None:
        self.critique = critique
        self.calls: list[JsonObject] = []

    async def chat(
        self,
        messages: object,
        *,
        response_model: type[ReflectionCritiqueResult],
        llm_context: JsonObject,
    ) -> ReflectionCritiqueResult:
        self.calls.append(
            {
                "messages": str(messages),
                "response_model": response_model.__name__,
                "llm_context": llm_context,
            }
        )
        return self.critique


def _container(runtime: RecordingWorkflowRuntime) -> FlowRuntimeContainer:
    return cast(FlowRuntimeContainer, RuntimeContainer(runtime))


def _policy() -> CriticPolicy:
    return CriticPolicy(
        policy_id="final-answer-safety",
        gate="final_answer",
        target=ReflectionTarget(kind="response"),
        instruction="Block unsafe or unsupported final answers.",
        criteria=[
            CriticCriterion(
                criterion_id="safety",
                description="The answer must not instruct destructive production actions.",
                severity="critical",
            ),
            CriticCriterion(
                criterion_id="evidence",
                description="The answer must be supported by visible facts.",
                severity="error",
            ),
        ],
        min_confidence=0.8,
        block_on_severities=["error", "critical"],
    )


def _node_config() -> JsonObject:
    return {
        "type": NodeType.REFLECTION.value,
        "llm": {"model": "mock-gpt-4", "temperature": 0.0},
        "critic_policy": _policy().model_dump(mode="json"),
    }


def _state() -> ExecutionState:
    state = ExecutionState(
        task_id="task",
        context_id="ctx",
        user_id="user",
        session_id="reflection_flow:ctx",
        response="Run destructive migration on production without approval.",
    )
    state.attach_durable_node_context(
        execution_branch_id="branch-1",
        node_schedule_sequence=7,
        superstep_sequence=6,
    )
    return state


def test_reflection_node_config_is_strict() -> None:
    config = NodeConfig(
        node_id="critic",
        type=NodeType.REFLECTION,
        name="Critic",
        llm=NodeLLMConfig(model="mock-gpt-4"),
        critic_policy=_policy(),
    )

    assert config.type is NodeType.REFLECTION
    assert config.critic_policy is not None
    assert config.critic_policy.policy_id == "final-answer-safety"

    with pytest.raises(ValueError, match="critic_policy"):
        _ = NodeConfig(
            node_id="bad",
            type=NodeType.REFLECTION,
            name="Bad",
            llm=NodeLLMConfig(model="mock-gpt-4"),
        )


@pytest.mark.asyncio
async def test_reflection_node_blocks_final_answer_gate_and_records_typed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    critique = ReflectionCritiqueResult(
        decision="blocked",
        confidence=0.98,
        summary="The answer asks for destructive production action without approval.",
        issues=[
            ReflectionCritiqueIssue(
                criterion_id="safety",
                severity="critical",
                finding="Destructive production migration is proposed.",
                evidence="The response says to run destructive migration on production.",
                required_action="Require explicit approval and a reversible migration plan.",
            )
        ],
    )
    fake_llm = FakeCriticLLM(critique)
    monkeypatch.setattr(runtime_nodes, "get_llm", lambda **_: fake_llm)
    runtime = RecordingWorkflowRuntime()
    node = ReflectionNode("critic", _node_config(), container=_container(runtime))
    state = _state()

    result = await node.run(state)

    assert result is state
    assert state.response == "Run destructive migration on production without approval."
    assert state.validation is not None
    assert state.validation["approved"] is False
    assert state.validation["gate"] == "final_answer"
    assert state.validation["critique"]["decision"] == "blocked"
    assert state.reflection_history[0].result.approved is False
    assert state.reflection_history[0].node_schedule_sequence == 7
    assert len(fake_llm.calls) == 1
    assert runtime.scheduled[0]["activity_type"] == "reflection"
    assert runtime.scheduled[0]["idempotency_key"] == runtime.scheduled[0]["activity_id"]
    assert runtime.scheduled[0]["side_effect_policy"] == SideEffectPolicy.idempotent.value
    assert runtime.completed[0]["result_json"] is not None
    assert sorted(runtime.completed[0]["result_json"].keys()) == ["result"]


@pytest.mark.asyncio
async def test_reflection_activity_replays_without_second_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    critique = ReflectionCritiqueResult(
        decision="approved",
        confidence=0.95,
        summary="The answer is supported and safe.",
        issues=[],
    )
    fake_llm = FakeCriticLLM(critique)
    monkeypatch.setattr(runtime_nodes, "get_llm", lambda **_: fake_llm)
    runtime = RecordingWorkflowRuntime()
    node = await create_node("critic", _node_config(), container=_container(runtime))
    assert isinstance(node, ReflectionNode)

    first_state = _state()
    first_state.response = "Use the approved staged migration plan."
    first_result = await node.run(first_state)

    second_state = _state()
    second_state.response = "Use the approved staged migration plan."
    second_result = await node.run(second_state)

    assert first_result.validation == second_result.validation
    assert first_result.reflection_history[0].result == second_result.reflection_history[0].result
    assert len(fake_llm.calls) == 1
    assert len(runtime.scheduled) == 2
    assert len(runtime.started) == 1
    assert len(runtime.completed) == 1
    assert second_state.validation is not None
    assert second_state.validation["approved"] is True


@pytest.mark.asyncio
async def test_reflection_node_requires_durable_workflow_context() -> None:
    node = ReflectionNode(
        "critic",
        _node_config(),
        container=_container(NoWorkflowRuntime()),
    )

    with pytest.raises(RuntimeError, match="requires durable workflow instance"):
        _ = await node.run(_state())
