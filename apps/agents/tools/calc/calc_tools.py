"""
Инструменты для калькулятора.
"""

from apps.agents.services.tool_decorator import tool


@tool(is_public=True, group="Математика", title="Калькулятор")
def calculate(expression: str) -> str:
    """
    Вычислить математическое выражение.

    Args:
        expression: Математическое выражение (например, "2+2", "10*5")
    """
    try:
        # Простая безопасная оценка только основных операций
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return f"Ошибка: недопустимые символы в выражении '{expression}'"

        # Заменяем операторы на безопасные
        expression = expression.replace(" ", "")

        # Простая проверка на деление на ноль
        if "/0" in expression:
            return "Ошибка: деление на ноль"

        result = eval(expression)
        return f"Результат: {expression} = {result}"

    except ZeroDivisionError:
        return "Ошибка: деление на ноль"
    except Exception as e:
        return f"Ошибка вычисления: {str(e)}"


@tool(is_public=True, group="Математика", title="Справка по математике")
def get_math_help() -> str:
    """
    Получить справку по математическим операциям.
    """
    return """
Доступные операции:
- Сложение: + (например, 5+3)
- Вычитание: - (например, 10-4) 
- Умножение: * (например, 6*7)
- Деление: / (например, 15/3)
- Скобки: () (например, (2+3)*4)
"""


# Список доступных инструментов для экспорта
CALC_TOOLS = [
    calculate,
    get_math_help,
]
