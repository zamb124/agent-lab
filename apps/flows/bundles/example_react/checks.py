"""
Функции проверки для evaluation тест-кейсов example_react flow.

Демонстрирует:
- checker функции: (state, response) -> bool
- universal функции: (None) -> input, (state, response) -> bool
"""

from core.types import JsonObject


def check_calculator_result(state: JsonObject, response: str) -> bool:
    """
    Проверяет что ответ калькулятора содержит число 42.

    Args:
        state: State после выполнения
        response: Ответ агента

    Returns:
        True если ответ содержит "42"
    """
    _ = state
    return "42" in response


def check_greeting(state: JsonObject, response: str) -> bool:
    """Проверяет что агент поприветствовал пользователя."""
    _ = state
    response_lower = response.lower()
    greetings = ["привет", "здравствуй", "добро пожаловать", "рад", "hello"]
    return any(g in response_lower for g in greetings)


def check_help_response(state: JsonObject, response: str) -> bool:
    """Проверяет что агент рассказал о своих возможностях."""
    _ = state
    response_lower = response.lower()
    keywords = ["калькулятор", "вычисл", "помо", "могу", "умею"]
    return any(k in response_lower for k in keywords)


def check_concise_length(state: JsonObject, response: str) -> bool:
    """Проверяет что ответ короткий (для concise skill)."""
    _ = state
    return len(response) <= 200


def check_detailed_response(state: JsonObject, response: str) -> bool:
    """Проверяет что ответ подробный (для detailed skill)."""
    _ = state
    return len(response) >= 200


def check_state_has_response(state: JsonObject, response: str) -> bool:
    """Проверяет что state содержит response."""
    _ = response
    return state.get("response") is not None


def universal_test_function(
    state: JsonObject | None = None,
    response: str | None = None,
) -> str | bool:
    """
    Универсальная функция: sender + checker в одном.

    - Без state: возвращает input для отправки
    - Со state: проверяет результат

    Args:
        state: None для режима sender, dict для режима checker
        response: Ответ агента (только в режиме checker)

    Returns:
        str (input) в режиме sender, bool в режиме checker
    """
    if state is None:
        # Режим sender - возвращаем input
        return "Привет! Как дела?"

    # Режим checker - проверяем ответ
    if not response:
        return False

    # Проверяем что есть хоть какой-то ответ
    return len(response) > 5


def check_file_processed(state: JsonObject, response: str) -> bool:
    """Проверяет что агент обработал файл."""
    _ = state
    keywords = ["файл", "текст", "содержит", "строк", "анализ"]
    response_lower = response.lower()
    return any(k in response_lower for k in keywords)
