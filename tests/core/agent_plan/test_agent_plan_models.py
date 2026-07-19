"""Unit tests for AgentPlan domain model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.agent_plan.models import (
    AgentPlan,
    AgentPlanStep,
    AgentPlanStepStatus,
    AgentPlanStepWriteInput,
    steps_from_write_inputs,
)


def test_agent_plan_create_assigns_id_and_steps() -> None:
    plan = AgentPlan.create(
        [
            AgentPlanStep(step_id="1", title="A", status=AgentPlanStepStatus.IN_PROGRESS),
            AgentPlanStep(step_id="2", title="B", status=AgentPlanStepStatus.PENDING),
        ]
    )
    assert plan.agent_plan_id
    assert len(plan.steps) == 2
    assert plan.steps[0].status == AgentPlanStepStatus.IN_PROGRESS


def test_agent_plan_rejects_duplicate_step_ids() -> None:
    with pytest.raises(ValidationError):
        AgentPlan.create(
            [
                AgentPlanStep(step_id="1", title="A"),
                AgentPlanStep(step_id="1", title="B"),
            ]
        )


def test_agent_plan_rejects_multiple_in_progress() -> None:
    with pytest.raises(ValidationError):
        AgentPlan.create(
            [
                AgentPlanStep(step_id="1", title="A", status=AgentPlanStepStatus.IN_PROGRESS),
                AgentPlanStep(step_id="2", title="B", status=AgentPlanStepStatus.IN_PROGRESS),
            ]
        )


def test_steps_from_write_inputs_maps_id_to_step_id() -> None:
    steps = steps_from_write_inputs(
        [
            AgentPlanStepWriteInput(id="1", title="Find", status=AgentPlanStepStatus.COMPLETED),
            AgentPlanStepWriteInput(id="2", title="Read", status=AgentPlanStepStatus.IN_PROGRESS),
        ]
    )
    assert steps[0].step_id == "1"
    assert steps[1].status == AgentPlanStepStatus.IN_PROGRESS


def test_steps_from_write_inputs_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        steps_from_write_inputs([])
