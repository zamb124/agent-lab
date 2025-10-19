"""
Инструменты для работы с сессионным хранилищем.
Позволяют агентам сохранять и получать данные между запросами.

Декоратор @tool автоматически оборачивает в Command если state изменился.
"""

import logging

from app.core.tool_decorator import tool
from app.core.variables import get_state

logger = logging.getLogger(__name__)


@tool(state_aware=True)
def session_set(key: str, value: str) -> str:
    """
    Сохраняет значение в сессионное хранилище.
    Данные доступны во всех агентах текущей сессии между запросами.
    
    Args:
        key: Ключ для сохранения
        value: Значение для сохранения
        
    Returns:
        Сообщение об успешном сохранении
        
    Examples:
        session_set("user_warehouse", "Склад Большие Каменщики")
        session_set("courier_id", "12345")
    """
    state = get_state()
    if not state:
        raise ValueError("State недоступен")
    
    if "store" not in state:
        state["store"] = {}
    
    state["store"][key] = value
    logger.info(f"📦 Сохранено в сессию: {key} = {value}")
    
    # Декоратор автоматически обернет в Command если state изменился!
    return f"Сохранено: {key}"


@tool(state_aware=True)
def session_get(key: str) -> str:
    """
    Получает значение из сессионного хранилища.
    
    Args:
        key: Ключ для получения
        
    Returns:
        Значение из хранилища или сообщение что ключ не найден
        
    Examples:
        session_get("user_warehouse")
        session_get("courier_id")
    """
    state = get_state()
    if not state:
        raise ValueError("State недоступен из контекста")
    
    store = state.get("store", {})
    value = store.get(key)
    
    if value is None:
        logger.info(f"📦 Ключ не найден в сессии: {key}")
        return f"Ключ '{key}' не найден в сессии"
    
    logger.info(f"📦 Получено из сессии: {key} = {value}")
    return str(value)


@tool
def session_has(key: str) -> str:
    """
    Проверяет существует ли ключ в сессионном хранилище.
    
    Args:
        key: Ключ для проверки
        
    Returns:
        "yes" если ключ существует, "no" если не существует
        
    Examples:
        session_has("user_warehouse")
    """
    state = get_state()
    if not state:
        return "no"
    
    store = state.get("store", {})
    exists = key in store
    
    logger.info(f"📦 Проверка ключа в сессии: {key} = {exists}")
    return "yes" if exists else "no"


@tool
def session_delete(key: str) -> str:
    """
    Удаляет значение из сессионного хранилища.
    
    Args:
        key: Ключ для удаления
        
    Returns:
        Сообщение об успешном удалении
        
    Examples:
        session_delete("temp_data")
    """
    state = get_state()
    if not state:
        raise ValueError("State недоступен из контекста")
    
    store = state.get("store", {})
    if key in store:
        del store[key]
        logger.info(f"📦 Удалено из сессии: {key}")
        return f"Ключ '{key}' удален"
    
    return f"Ключ '{key}' не найден"


@tool
def session_keys() -> str:
    """
    Возвращает список всех ключей в сессионном хранилище.
    
    Returns:
        Строка со списком ключей через запятую
        
    Examples:
        session_keys()
    """
    state = get_state()
    if not state:
        return "Ошибка: State недоступен"
    
    store = state.get("store", {})
    keys = list(store.keys())
    
    if not keys:
        return "Хранилище пусто"
    
    logger.info(f"📦 Ключи в сессии: {keys}")
    return ", ".join(keys)


@tool
def get_variable(name: str) -> str:
    """
    Получает переменную из flow или компании.
    Переменные задаются в конфигурации flow/компании.
    
    Args:
        name: Имя переменной
        
    Returns:
        Значение переменной или сообщение что переменная не найдена
        
    Examples:
        get_variable("company_name")
        get_variable("bot_name")
        get_variable("support_email")
    """
    from app.core.context import get_context
    from app.core.variables import VariableResolver
    
    context = get_context()
    if not context:
        return "Ошибка: контекст недоступен"
    
    variables = VariableResolver.resolve_all()
    value = variables.get(name)
    
    if value is None:
        logger.info(f"📦 Переменная не найдена: {name}")
        available = ", ".join(list(variables.keys())[:10])
        return f"Переменная '{name}' не найдена. Доступные: {available}"
    
    logger.info(f"📦 Получена переменная: {name} = {value}")
    return str(value)
