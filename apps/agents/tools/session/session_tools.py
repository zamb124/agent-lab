"""
Инструменты для работы с сессионным хранилищем.
Позволяют агентам сохранять и получать данные между запросами.

Декоратор @tool автоматически оборачивает в Command если state изменился.
"""

import logging

from apps.agents.services.tool_decorator import tool
from core.variables import get_state
from apps.agents.services.state_manager import StoreProxy

logger = logging.getLogger(__name__)


@tool(state_aware=True, group="Хранение данных")
async def session_set(key: str, value: str) -> str:
    """
    Сохраняет значение в сессионное хранилище.
    StoreProxy автоматически сохраняет в БД при изменении.
    """
    print(f"🔵🔵🔵 session_set ВЫЗВАН: key={key}, value={value}")
    logger.info(f"🔵 session_set ВЫЗВАН: key={key}, value={value}")
    state = get_state()
    session_id = state["session_id"]
    
    print(f"🔵🔵🔵 session_set: session_id={session_id}")
    logger.info(f"🔵 session_set: session_id={session_id}")
    
    # store_id всегда определяется однозначно
    store_id = state.get("store_id")
    if not store_id:
        # Для sub-сессий: store_id = parent_session_id (извлекается из session_id)
        # Для обычных: store_id = session_id
        store_id = session_id.split(":sub:")[0] if ":sub:" in session_id else session_id
    
    print(f"🔵🔵🔵 session_set: store_id={store_id}")
    logger.info(f"🔵 session_set: store_id={store_id}")
    
    # Убеждаемся что store - это StoreProxy с правильным store_id
    if "store" not in state or not isinstance(state["store"], StoreProxy) or state["store"].store_id != store_id:
        print(f"🔵🔵🔵 session_set: создаем новый StoreProxy для store_id={store_id}")
        logger.info(f"🔵 session_set: создаем новый StoreProxy для store_id={store_id}")
        from apps.agents.services.state_manager import get_state_manager
        state_manager = await get_state_manager()
        store_data = await state_manager.load_store(store_id)
        state["store"] = StoreProxy(store_id, store_data)
        state["store_id"] = store_id
    
    # Изменяем store - StoreProxy автоматически сохранит в БД
    print(f"🔵🔵🔵 session_set: ДО изменения store={dict(state['store'])}")
    logger.info(f"🔵 session_set: ДО изменения store={dict(state['store'])}")
    state["store"][key] = value
    print(f"🔵🔵🔵 session_set: ПОСЛЕ изменения store={dict(state['store'])}")
    logger.info(f"🔵 session_set: ПОСЛЕ изменения store={dict(state['store'])}")
    
    # Сохраняем сразу в БД чтобы субагенты видели изменения
    import asyncio
    await state["store"].ensure_saved()
    
    logger.info(f"📦 session_set: key={key}, value={value}, store_id={store_id}, session_id={session_id}, store={dict(state['store'])}")
    return f"Сохранено: {key}"


@tool(state_aware=True, group="Хранение данных")
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


@tool(group="Хранение данных")
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


@tool(group="Хранение данных")
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


@tool(group="Хранение данных")
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


@tool(group="Хранение данных")
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
    from core.context import get_context
    from core.variables import VariableResolver
    
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
