"""
Final Answer - инструмент для финального ответа с обоснованием.
"""

from typing import List, Optional

from apps.agents.src.tools import tool
from apps.agents.src.tools.base import ToolType


@tool(
    name="final_answer",
    description="Формирует финальный обоснованный ответ. Требует указать ответ, обоснование, уверенность и источники.",
    tags=["validation"],
    tool_type=ToolType.EXIT,
)
async def final_answer(
    answer: str,
    justification: str,
    confidence: float,
    sources: List[str] = None,
    state: Optional[dict] = None,
) -> dict:
    """Возвращает структурированный ответ."""
    return {
        "answer": answer,
        "justification": justification,
        "confidence": confidence,
        "sources": sources or [],
    }
