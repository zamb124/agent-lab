"""
Агент-калькулятор для математических вычислений.
"""

from app.agents.react_agent import ReActAgent
from app.tools.standard import ask_user
from app.tools.calc_tools import calculate, get_math_help


class CalculatorAgent(ReActAgent):
    """Агент для математических вычислений"""

    name = "calculator_agent"
    description = "Помогает с математическими вычислениями"

    prompt = """
Ты калькулятор-помощник.

Твоя задача:
1. Если пользователь дал неполное выражение (например, "Посчитай 2+2") - извлеки математическое выражение и вычисли
2. Если выражение неясно - спроси уточнение у пользователя
3. Используй инструмент calculate для вычислений
4. Дай понятный ответ с объяснением

Будь точным и полезным в математических вопросах.
"""

    tools = [ask_user, calculate, get_math_help]
