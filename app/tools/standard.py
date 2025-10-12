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

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
