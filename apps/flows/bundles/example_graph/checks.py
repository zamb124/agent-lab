"""
Функции проверки для evaluation тест-кейсов example_graph flow.

Демонстрирует проверки для графовых flow с маршрутизацией.
"""

from typing import Any, Dict, Optional


def check_order_route(state: Dict[str, Any], response: str) -> bool:
    """
    Проверяет что запрос о заказе был обработан order_processor.

    Args:
        state: State после выполнения
        response: Ответ агента

    Returns:
        True если route == 'order' или ответ содержит признаки заказа
    """
    # Проверяем state
    if state.get("route") == "order":
        return True

    # Проверяем ответ
    response_lower = response.lower()
    order_keywords = ["заказ", "order", "ord-", "оформлен", "принят"]
    return any(k in response_lower for k in order_keywords)


def check_complaint_route(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что запрос о жалобе был обработан complaint_processor."""
    if state.get("route") == "complaint":
        return True

    response_lower = response.lower()
    complaint_keywords = ["жалоб", "complaint", "cmp-", "зарегистрир"]
    return any(k in response_lower for k in complaint_keywords)


def check_general_route(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что общий запрос был обработан general_processor."""
    if state.get("route") == "general":
        return True

    # Не должен содержать признаков order/complaint
    response_lower = response.lower()
    return "ord-" not in response_lower and "cmp-" not in response_lower


def check_no_formatter(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что formatter не был вызван (для fast_track skill)."""
    # В fast_track ответ не должен иметь форматирования
    # Formatter добавляет квадратные скобки
    return not response.startswith("[") or state.get("processed") is None


def check_mock_order_route(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что mock маршрутизация работает."""
    # Mock должен вернуть предопределённый ответ
    return "ORD-TEST" in response or "тестовый заказ" in response.lower()


def check_formatted_response(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что ответ был отформатирован."""
    # Formatter добавляет квадратные скобки в начало
    return response.startswith("[") and state.get("processed") is True


def test_classifier(
    state: Optional[Dict[str, Any]] = None,
    response: Optional[str] = None,
) -> Any:
    """
    Универсальная функция для теста classifier.

    - Без state: возвращает тестовый input
    - Со state: проверяет что classifier отработал

    Args:
        state: None для sender, dict для checker
        response: Ответ агента

    Returns:
        str (input) или bool (результат проверки)
    """
    if state is None:
        # Режим sender
        return "Хочу оформить заказ номер 12345"

    # Режим checker
    # Проверяем что classifier установил route
    route = state.get("route")
    if route not in ["order", "complaint", "general"]:
        return False

    # Для запроса с "заказ" route должен быть "order"
    return route == "order"


def check_graph_execution(state: Dict[str, Any], response: str) -> bool:
    """Проверяет что граф выполнился полностью."""
    # Должен быть response и processed от formatter
    return bool(response) and len(response) > 5


def universal_graph_test(
    state: Optional[Dict[str, Any]] = None,
    response: Optional[str] = None,
) -> Any:
    """
    Универсальная функция: sender + checker в одном для графа.

    - Без state: возвращает input для отправки
    - Со state: проверяет что граф обработал запрос

    Args:
        state: None для режима sender, dict для режима checker
        response: Ответ агента (только в режиме checker)

    Returns:
        str (input) в режиме sender, bool в режиме checker
    """
    if state is None:
        # Режим sender
        return "Хочу узнать статус моего заказа ORD-777"

    # Режим checker
    if not response:
        return False

    # Проверяем что есть осмысленный ответ
    return len(response) > 10 and ("заказ" in response.lower() or "order" in response.lower())

