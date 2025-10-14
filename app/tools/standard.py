"""
Стандартные инструменты для всех агентов.
"""

from langgraph.types import interrupt

from app.core.tool_decorator import tool


@tool
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
    result = interrupt(question)
    formatted_result = f"QUESTION: {question}\nANSWER: {result}"
    return formatted_result


# Импортируем сессионные тулы

# Список доступных инструментов для экспорта
STANDARD_TOOLS = [
    ask_user,
]
