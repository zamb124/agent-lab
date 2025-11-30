"""
Стандартные инструменты для всех агентов.
"""

from apps.agents.exceptions import AgentInterrupt
from core.variables import get_state
from langchain_core.messages import HumanMessage

from apps.agents.services.tool_decorator import tool


@tool(group="Система", state_aware=True)
async def ask_user(question: str) -> str:
    """
    Запрашивает информацию у пользователя.
    Если нужно задать вопрос - вызывай эту функцию.
    
    Args:
        question: Вопрос для пользователя
    """
    state = get_state()
    
    if not state or not state.get("interrupt_context"):
        raise AgentInterrupt(question)
    
    state.pop("interrupt_context", None)
    messages = state.get("messages", [])
    
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return f"QUESTION: {question}\nANSWER: {message.content}"
    
    raise AgentInterrupt(question)


# Импортируем сессионные тулы

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
