"""
Стандартные инструменты для всех агентов.
"""

from app.agents.base import AgentInterrupt
from app.core.variables import get_state
from langchain_core.messages import HumanMessage

from app.core.tool_decorator import tool


@tool(group="Система", state_aware=False)
def ask_user(question: str) -> str:
    """
    ⚠️ ОБЯЗАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ВОПРОСОВ К ПОЛЬЗОВАТЕЛЮ ⚠️
    
    КОГДА ИСПОЛЬЗОВАТЬ:
    - Если нужна информация от пользователя - ВСЕГДА вызывай ИМЕННО ЭТУ функцию
    - НЕ отвечай текстом напрямую если нужно задать вопрос
    - НЕ пиши "Куда бы вы хотели..." - вызови ask_user("Куда бы вы хотели...")
    
    ПРАВИЛЬНО: ask_user("Куда вы хотите поехать?")
    НЕПРАВИЛЬНО: "Куда вы хотите поехать?" (текстом)

    Args:
        question: Вопрос для пользователя

    Returns:
        Ответ пользователя в формате "QUESTION: вопрос\nANSWER: ответ"
    """
    state = get_state()
    if state and state.get("interrupt_context") and state.get("messages") and isinstance(state["messages"][-1], HumanMessage):
        state.pop("interrupt_context", None)
        return f"QUESTION: {question}\nANSWER: {state['messages'][-1].content}"
    raise AgentInterrupt(question)


# Импортируем сессионные тулы

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
