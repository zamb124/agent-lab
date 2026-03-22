"""Функции для example_graph flow."""

from typing import Dict, Any


def format_response(state: Dict[str, Any]) -> Dict[str, Any]:
    """Форматирует финальный ответ.
    
    Добавляет метаданные о маршруте обработки.
    Проверяет разные поля state в зависимости от маршрута.
    """
    route = state.get("route", "unknown")
    
    # Проверяем возможные поля в зависимости от маршрута
    possible_fields = {
        "greeting": ["greeting_message", "response"],
        "order": ["order_total", "response"],
        "cat": ["cat_fact", "response"],
    }
    
    # Берем первое найденное поле или response по умолчанию
    fields_to_check = possible_fields.get(route, ["response"])
    response = ""
    
    for field in fields_to_check:
        value = state.get(field)
        if value is not None:
            response = str(value)
            break
    
    state["response"] = f"[{route.upper()}] {response}"
    state["processed"] = True
    
    return state

