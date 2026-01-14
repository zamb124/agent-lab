"""
AskUser - инструмент для запроса информации у пользователя.
"""

from typing import Optional

from apps.agents.src.agent.exceptions import AgentInterrupt
from apps.agents.src.tools import tool


@tool(
    name="ask_user",
    description="Задает вопрос пользователю и ожидает ответ. Используй когда нужна информация от пользователя.",
    tags=["misc"],
)
async def ask_user(question: str, state: Optional[dict] = None) -> str:
    """Запрашивает ввод у пользователя через interrupt."""
    raise AgentInterrupt(question=question)
