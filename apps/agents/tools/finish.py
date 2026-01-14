"""
Finish - инструмент для завершения выполнения агента.
"""

from typing import Optional

from apps.agents.src.tools import tool
from apps.agents.src.tools.base import ToolType


@tool(
    name="finish",
    description="Завершает выполнение и возвращает финальный ответ пользователю",
    tags=["misc"],
    tool_type=ToolType.EXIT,
)
async def finish(answer: str, state: Optional[dict] = None) -> str:
    """Возвращает финальный ответ."""
    return answer
