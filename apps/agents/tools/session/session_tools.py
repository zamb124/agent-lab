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
    await state["store"].ensure_saved()
    
    logger.info(f"📦 session_set: key={key}, value={value}, store_id={store_id}, session_id={session_id}, store={dict(state['store'])}")
    return f"Сохранено: {key}"


@tool(state_aware=True, group="Хранение данных")
async def session_get(key: str) -> str:
    """Получает значение из сессионного хранилища."""
    state = get_state()
    if not state:
        raise ValueError("State недоступен из контекста")
    
    store = state.get("store", {})
    value = store.get(key)
    
    if value is None:
        return f"Ключ '{key}' не найден в сессии"
    
    return str(value)


@tool(group="Хранение данных", state_aware=True)
async def session_has(key: str) -> str:
    """Проверяет существует ли ключ в сессионном хранилище."""
    state = get_state()
    if not state:
        return "no"
    
    store = state.get("store", {})
    return "yes" if key in store else "no"


@tool(group="Хранение данных", state_aware=True)
async def session_delete(key: str) -> str:
    """Удаляет значение из сессионного хранилища."""
    state = get_state()
    if not state:
        raise ValueError("State недоступен из контекста")
    
    store = state.get("store", {})
    if key in store:
        del store[key]
        return f"Ключ '{key}' удален"
    
    return f"Ключ '{key}' не найден"


@tool(group="Хранение данных", state_aware=True)
async def session_keys() -> str:
    """Возвращает список всех ключей в сессионном хранилище."""
    state = get_state()
    if not state:
        return "Ошибка: State недоступен"
    
    store = state.get("store", {})
    keys = list(store.keys())
    
    if not keys:
        return "Хранилище пусто"
    
    return ", ".join(keys)


@tool(group="Хранение данных")
async def get_variable(name: str) -> str:
    """Получает переменную из flow или компании."""
    from core.context import get_context
    from core.variables import VariableResolver
    
    context = get_context()
    if not context:
        return "Ошибка: контекст недоступен"
    
    variables = VariableResolver.resolve_all()
    value = variables.get(name)
    
    if value is None:
        available = ", ".join(list(variables.keys())[:10])
        return f"Переменная '{name}' не найдена. Доступные: {available}"
    
    return str(value)
