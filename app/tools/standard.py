"""
Стандартные инструменты для всех агентов.
"""

from langgraph.types import interrupt

from app.core.tool_decorator import tool


@tool
def ask_user(question: str) -> str:
    """
    Запросить информацию у пользователя.

    Args:
        question: Вопрос для пользователя

    Returns:
        Ответ пользователя в формате "QUESTION: вопрос\nANSWER: ответ"
    """
    result = interrupt(question)
    formatted_result = f"QUESTION: {question}\nANSWER: {result}"
    return formatted_result


# Импортируем сессионные тулы
from app.tools.session_tools import (
    session_set,
    session_get, 
    session_has,
    session_delete,
    session_keys,
    get_variable
)

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
