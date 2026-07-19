"""
Тулы AgentPlan для llm_node: write (full replace) и get.

План хранится в ExecutionState.agent_plan; каждый write полностью перетирает.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from core.agent_plan.models import (
    AgentPlan,
    AgentPlanStepWriteInput,
    steps_from_write_inputs,
)
from core.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from core.state import ExecutionState


class AgentPlanWriteArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    steps: list[AgentPlanStepWriteInput] = Field(
        ...,
        min_length=1,
        description=(
            "Полный актуальный список шагов (replace). "
            "Всегда передавай весь список, не дельту. "
            "Не больше одного шага со статусом in_progress."
        ),
    )


class AgentPlanGetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


def _plan_block(plan: AgentPlan) -> JsonObject:
    return {
        "type": "agent_plan",
        "plan": plan.model_dump(mode="json"),
    }


def _plan_payload(plan: AgentPlan) -> JsonObject:
    return {
        "agent_plan_id": plan.agent_plan_id,
        "plan": plan.model_dump(mode="json"),
        "blocks": [_plan_block(plan)],
    }


def _parse_write_steps(steps: list[JsonValue]) -> list[AgentPlanStepWriteInput]:
    parsed: list[AgentPlanStepWriteInput] = []
    for item in steps:
        parsed.append(AgentPlanStepWriteInput.model_validate(item))
    return parsed


@tool(
    name="agent_plan_write",
    description=(
        "Создаёт или полностью перезаписывает план выполнения агента (checklist шагов). "
        "Всегда передавай полный список steps. Хранится в state; UI показывает checklist."
    ),
    tags=["planning", "misc"],
    parameters_model=AgentPlanWriteArgs,
)
async def agent_plan_write(
    steps: list[JsonValue],
    *,
    state: "ExecutionState",
) -> JsonObject:
    plan_steps = steps_from_write_inputs(_parse_write_steps(steps))
    previous = state.agent_plan
    plan = AgentPlan.create(
        plan_steps,
        agent_plan_id=previous.agent_plan_id if previous is not None else None,
    )
    state.agent_plan = plan
    return _plan_payload(plan)


@tool(
    name="agent_plan_get",
    description="Возвращает текущий AgentPlan из state. Если плана ещё нет — ошибка: сначала agent_plan_write.",
    tags=["planning", "misc"],
    parameters_model=AgentPlanGetArgs,
)
async def agent_plan_get(*, state: "ExecutionState") -> JsonObject:
    plan = state.agent_plan
    if plan is None:
        raise ValueError("agent_plan_get: plan is missing; call agent_plan_write first")
    return _plan_payload(plan)
