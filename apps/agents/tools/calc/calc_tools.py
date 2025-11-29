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
    from simpleeval import simple_eval
    
    try:
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            raise ValueError(f"Недопустимые символы в выражении '{expression}'")

        expression_clean = expression.replace(" ", "")

        if "/0" in expression_clean:
            raise ZeroDivisionError("Деление на ноль")

        result = simple_eval(expression_clean)
        return f"Результат: {expression} = {result}"

    except ZeroDivisionError as e:
        raise ValueError(f"Ошибка: {str(e)}") from e
    except Exception as e:
        raise ValueError(f"Ошибка вычисления: {str(e)}") from e


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
