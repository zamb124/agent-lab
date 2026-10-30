"""Доменные модели AgentPlan (flat checklist в ExecutionState)."""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from core.models import StrictBaseModel


class AgentPlanStepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEED_HELP = "need_help"
    FAILED = "failed"


class AgentPlanStep(StrictBaseModel):
    """Один шаг плана агента."""

    step_id: str = Field(..., min_length=1, description="Стабильный id шага")
    title: str = Field(..., min_length=1, description="Краткий заголовок шага")
    status: AgentPlanStepStatus = Field(
        default=AgentPlanStepStatus.PENDING,
        description="Статус шага",
    )


class AgentPlan(StrictBaseModel):
    """Активный план выполнения агента (один на ExecutionState)."""

    agent_plan_id: str = Field(..., min_length=1, description="Id плана")
    title: str | None = Field(default=None, description="Опциональный заголовок плана")
    steps: list[AgentPlanStep] = Field(..., min_length=1, description="Плоский список шагов")

    @field_validator("steps")
    @classmethod
    def _require_unique_step_ids(cls, steps: list[AgentPlanStep]) -> list[AgentPlanStep]:
        seen: set[str] = set()
        for step in steps:
            if step.step_id in seen:
                raise ValueError(f"duplicate step_id: {step.step_id}")
            seen.add(step.step_id)
        return steps

    @model_validator(mode="after")
    def _at_most_one_in_progress(self) -> AgentPlan:
        in_progress = sum(
            1 for step in self.steps if str(step.status) == AgentPlanStepStatus.IN_PROGRESS.value
        )
        if in_progress > 1:
            raise ValueError("AgentPlan allows at most one step with status in_progress")
        return self

    @classmethod
    def create(
        cls,
        steps: list[AgentPlanStep],
        *,
        title: str | None = None,
        agent_plan_id: str | None = None,
    ) -> AgentPlan:
        resolved_id = agent_plan_id if agent_plan_id else str(uuid4())
        return cls(agent_plan_id=resolved_id, title=title, steps=steps)


class AgentPlanStepWriteInput(StrictBaseModel):
    """Плоский шаг в args тула agent_plan_write (LLM: id/title/status)."""

    id: str = Field(..., min_length=1, description="Короткий стабильный id шага (1, 2, …).")
    title: str = Field(..., min_length=1, description="Одна фраза — что сделать.")
    status: AgentPlanStepStatus = Field(
        ...,
        description="pending | in_progress | completed | need_help | failed.",
    )


def steps_from_write_inputs(steps: list[AgentPlanStepWriteInput]) -> list[AgentPlanStep]:
    if not steps:
        raise ValueError("agent_plan_write: steps must be non-empty")
    return [
        AgentPlanStep(step_id=item.id, title=item.title, status=item.status)
        for item in steps
    ]
