"""
Инструменты для калькулятора.
"""

from apps.agents.services.tool_decorator import tool


@tool(is_public=True, group="Математика", title="Калькулятор")
async def calculate(expression: str) -> str:
    """Вычислить математическое выражение."""
    from simpleeval import simple_eval
    
    allowed_chars = set("0123456789+-*/.() ")
    if not all(c in allowed_chars for c in expression):
        raise ValueError(f"Недопустимые символы в выражении '{expression}'")

    expression_clean = expression.replace(" ", "")

    if "/0" in expression_clean:
        raise ValueError("Деление на ноль")

    result = simple_eval(expression_clean)
    return f"Результат: {expression} = {result}"


@tool(is_public=True, group="Математика", title="Справка по математике")
async def get_math_help() -> str:
    """Получить справку по математическим операциям."""
    return """Доступные операции:
- Сложение: + (5+3)
- Вычитание: - (10-4) 
- Умножение: * (6*7)
- Деление: / (15/3)
- Скобки: () ((2+3)*4)"""


# Список доступных инструментов для экспорта
CALC_TOOLS = [
    calculate,
    get_math_help,
]
