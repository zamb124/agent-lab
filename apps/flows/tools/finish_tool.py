"""Lightweight ReAct exit tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools import tool

if TYPE_CHECKING:
    from core.state import ExecutionState


class FinishArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(..., min_length=1, description="Финальный текст, который увидит пользователь.")


@tool(
    name="finish",
    description="Завершает выполнение и возвращает финальный ответ пользователю",
    tags=["misc"],
    react_role=ReactToolRole.EXIT,
    args_schema=FinishArgs,
)
async def finish(answer: str, *, state: "ExecutionState") -> str:
    return answer


__all__ = ["FinishArgs", "finish"]
