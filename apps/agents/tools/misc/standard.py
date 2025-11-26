"""
Стандартные инструменты для всех агентов.
"""

from apps.agents.agents.base import AgentInterrupt
from core.variables import get_state
from langchain_core.messages import HumanMessage, AIMessage

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
    if state and state.get("messages"):
        messages = state.get("messages", [])
        # Ищем HumanMessage после последнего AIMessage с tool_call для ask_user
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if tool_call.get("name") == "ask_user":
                        # Ищем HumanMessage после этого AIMessage
                        for j in range(i + 1, len(messages)):
                            if isinstance(messages[j], HumanMessage):
                                if "interrupt_context" in state:
                                    state.pop("interrupt_context", None)
                                return f"QUESTION: {question}\nANSWER: {messages[j].content}"
                        break
    
    raise AgentInterrupt(question)


# Импортируем сессионные тулы

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
