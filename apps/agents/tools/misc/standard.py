"""
Стандартные инструменты для всех агентов.
"""

from apps.agents.exceptions import AgentInterrupt
from core.variables import get_state
from langchain_core.messages import HumanMessage

from apps.agents.services.tool_decorator import tool


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
