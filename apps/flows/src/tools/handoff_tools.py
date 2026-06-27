"""
Built-in tools для handoff/handback между flows.

handoff_to_flow — передача управления дочернему flow (используется в llm_node).
handback_to_parent — возврат управления родительскому flow.

Zero-Guess: variables передаются ЯВНО, никакого неявного мержа стейтов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools.decorator import tool
from core.state.interrupt import HandoffInterrupt
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState


class HandoffToFlowArgs(BaseModel):
    """Аргументы тула handoff_to_flow: передача управления другому flow."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_flow_id: str = Field(..., min_length=1, description="ID целевого flow (агента), которому передаётся управление")
    target_branch_id: str = Field(
        default="default",
        min_length=1,
        description="ID ветки целевого flow (по умолчанию 'default')",
    )
    reason: str | None = Field(default=None, description="Причина передачи управления (для UI пользователя)")
    variables: JsonObject = Field(
        default_factory=dict,
        description="Переменные, ЯВНО передаваемые дочернему flow. Мержатся поверх дефолтных переменных дочернего flow.",
    )


class HandbackToParentArgs(BaseModel):
    """Аргументы тула handback_to_parent: возврат управления родительскому flow."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    response: str = Field(..., min_length=1, description="Итоговый ответ/результат, возвращаемый родительскому flow")
    variables: JsonObject = Field(
        default_factory=dict,
        description="Переменные, ЯВНО возвращаемые родительскому flow. Пустой dict = ничего не возвращается.",
    )


@tool(
    name="handoff_to_flow",
    description=(
        "Передать управление другому агенту (flow). "
        "Родительский агент приостанавливается до возврата управления через handback. "
        "Переменные передаются ЯВНО — только то, что нужно дочернему агенту. "
        "Дочерний агент НЕ получает доступ к стейту родителя."
    ),
    tags=["flows", "handoff"],
    parameters_model=HandoffToFlowArgs,
)
async def handoff_to_flow(
    target_flow_id: str,
    target_branch_id: str = "default",
    reason: str | None = None,
    variables: JsonObject | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state

    target_name = target_flow_id
    question = f"Передаю управление агенту «{target_name}»"
    if reason:
        question += f". Причина: {reason}"

    interrupt_body = HandoffInterrupt(
        question=question,
        target_flow_id=target_flow_id,
        target_branch_id=target_branch_id,
        target_name=target_name,
        variables=variables or {},
        reason=reason,
    )

    raise FlowInterrupt(body=interrupt_body)


@tool(
    name="handback_to_parent",
    description=(
        "Вернуть управление родительскому агенту (flow) после handoff. "
        "Переменные возвращаются ЯВНО — только то, что нужно родителю. "
        "Всё остальное остаётся в стейте дочернего flow."
    ),
    tags=["flows", "handoff"],
    parameters_model=HandbackToParentArgs,
)
async def handback_to_parent(
    response: str,
    variables: JsonObject | None = None,
    *,
    state: "ExecutionState",
) -> str:
    state.response = response
    state.terminal_task_state = "handback"
    state.handback_return_variables = dict(variables) if variables else {}
    if variables:
        state.variables = {**state.variables, **variables}

    return response
