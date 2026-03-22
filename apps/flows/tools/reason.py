"""
Reason - инструмент для явного рассуждения агента.

Добавляется пользователем в список tools.
Runner автоматически определяет reasoning режим по наличию tool с tool_type=REASON.
Сохраняет рассуждения в state и эмитит как артефакт.
"""

from typing import Any, Dict, Optional

from apps.flows.src.tools import tool
from apps.flows.src.tools.base import ToolType


@tool(
    name="reason",
    description="Запиши свои рассуждения перед принятием решения. Опиши: что наблюдаешь, анализ ситуации, план действий, следующий шаг.",
    tags=["reasoning", "internal"],
    tool_type=ToolType.REASON,
)
async def reason(
    observation: str,
    analysis: str,
    plan: str,
    next_action: str,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Сохраняет рассуждения в state и возвращает подтверждение."""
    if state is not None:
        reasoning_entry = {
            "observation": observation,
            "analysis": analysis,
            "plan": plan,
            "next_action": next_action,
        }
        if "reasoning_history" not in state:
            state["reasoning_history"] = []
        state["reasoning_history"].append(reasoning_entry)
        state["pending_reasoning"] = reasoning_entry

    return f"Рассуждения записаны. Выполняй: {next_action}"

