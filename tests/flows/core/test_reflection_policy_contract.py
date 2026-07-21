"""Contract tests for CriticPolicy, ReflectionTarget, NodeConfig reflection rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models import NodeConfig, NodeLLMConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.flow_config import Edge, SimpleEdgeCondition
from apps.flows.src.models.node_config import ReactConfig, ReactLoopMode
from core.ai.llm_config import LLMCallConfig
from core.reflection import (
    CriticCriterion,
    CriticExit,
    CriticExitWhen,
    CriticPolicy,
    ReflectionTarget,
)
from tests.flows.fixtures.reflection import reflection_policy


def test_critic_policy_rejects_duplicate_criterion_ids() -> None:
    with pytest.raises(ValidationError, match="criterion_id"):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[
                CriticCriterion(criterion_id="a", description="one", severity="error"),
                CriticCriterion(criterion_id="a", description="two", severity="critical"),
            ],
            min_confidence=0.8,
            block_on_severities=["error"],
        )


def test_critic_policy_rejects_duplicate_block_severities() -> None:
    with pytest.raises(ValidationError, match="block_on_severities"):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[
                CriticCriterion(criterion_id="a", description="one", severity="error"),
            ],
            min_confidence=0.8,
            block_on_severities=["error", "error"],
        )


def test_critic_policy_rejects_empty_criteria() -> None:
    with pytest.raises(ValidationError):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[],
            min_confidence=0.8,
            block_on_severities=["error"],
        )


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_critic_policy_rejects_min_confidence_out_of_range(bad: float) -> None:
    with pytest.raises(ValidationError):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[
                CriticCriterion(criterion_id="a", description="one", severity="error"),
            ],
            min_confidence=bad,
            block_on_severities=["error"],
        )


def test_reflection_target_state_path_required() -> None:
    with pytest.raises(ValidationError, match="state_path"):
        ReflectionTarget(kind="state_path")


def test_reflection_target_state_path_forbidden_for_other_kinds() -> None:
    with pytest.raises(ValidationError, match="state_path"):
        ReflectionTarget(kind="response", state_path="variables.x")


def test_node_config_reflection_requires_critic_policy() -> None:
    with pytest.raises(ValidationError, match="critic_policy"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
        )


def test_node_config_reflection_requires_llm_model() -> None:
    with pytest.raises(ValidationError, match="llm.model"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model=None),
            critic_policy=reflection_policy(),
        )


def test_node_config_reflection_forbids_fallback_models() -> None:
    with pytest.raises(ValidationError, match="fallback_models"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(
                model="mock-gpt-4",
                fallback_models=[LLMCallConfig(model="mock-gpt-4")],
            ),
            critic_policy=reflection_policy(),
        )


def test_node_config_reflection_forbids_tools() -> None:
    with pytest.raises(ValidationError, match="tools"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
            critic_policy=reflection_policy(),
            tools=[{"tool_id": "calculator"}],
        )


def test_node_config_reflection_forbids_agent_skills() -> None:
    with pytest.raises(ValidationError, match="agent_skills"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
            critic_policy=reflection_policy(),
            agent_skills=["some-skill"],
        )


def test_node_config_reflection_forbids_prompt() -> None:
    with pytest.raises(ValidationError, match="prompt"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
            critic_policy=reflection_policy(),
            prompt="You are a critic",
        )


def test_node_config_reflection_forbids_react() -> None:
    with pytest.raises(ValidationError, match="react"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
            critic_policy=reflection_policy(),
            react=ReactConfig(loop_mode=ReactLoopMode.AUTO),
        )


def test_node_config_reflection_forbids_structured_output() -> None:
    with pytest.raises(ValidationError, match="structured_output"):
        NodeConfig(
            node_id="critic",
            type=NodeType.REFLECTION,
            name="Critic",
            llm=NodeLLMConfig(model="mock-gpt-4"),
            critic_policy=reflection_policy(),
            structured_output=True,
        )


def test_node_config_reflection_accepts_valid_policy() -> None:
    cfg = NodeConfig(
        node_id="critic",
        type=NodeType.REFLECTION,
        name="Critic",
        llm=NodeLLMConfig(model="mock-gpt-4"),
        critic_policy=reflection_policy(),
    )
    assert cfg.critic_policy is not None
    assert cfg.critic_policy.policy_id == "final-answer-safety"


def test_edge_from_port_accepted() -> None:
    edge = Edge(
        from_node="critic",
        to_node="ok",
        from_port="approved",
        condition=SimpleEdgeCondition(
            variable="validation.approved",
            operator="==",
            value=True,
        ),
    )
    assert edge.from_port == "approved"


def test_edge_from_port_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Edge(from_node="a", to_node="b", from_port="")


def test_critic_policy_rejects_duplicate_exit_ids() -> None:
    with pytest.raises(ValidationError, match="exit_id"):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[
                CriticCriterion(criterion_id="a", description="one", severity="error"),
            ],
            min_confidence=0.8,
            block_on_severities=["error"],
            exits=[
                CriticExit(
                    exit_id="same",
                    label="A",
                    when=CriticExitWhen(kind="approved_true"),
                ),
                CriticExit(
                    exit_id="same",
                    label="B",
                    when=CriticExitWhen(kind="approved_false"),
                ),
            ],
        )


def test_critic_policy_rejects_always_not_last() -> None:
    with pytest.raises(ValidationError, match="always"):
        CriticPolicy(
            policy_id="p",
            gate="final_answer",
            target=ReflectionTarget(kind="response"),
            instruction="x",
            criteria=[
                CriticCriterion(criterion_id="a", description="one", severity="error"),
            ],
            min_confidence=0.8,
            block_on_severities=["error"],
            exits=[
                CriticExit(
                    exit_id="catch",
                    label="Catch",
                    when=CriticExitWhen(kind="always"),
                ),
                CriticExit(
                    exit_id="pass",
                    label="Pass",
                    when=CriticExitWhen(kind="approved_true"),
                ),
            ],
        )


def test_critic_policy_default_exits_are_pass_fail() -> None:
    policy = reflection_policy()
    assert [item.exit_id for item in policy.exits] == ["approved", "blocked"]
