"""
Функции для рендеринга state переменных в промптах.
Используется в BaseAgent для динамической подстановки переменных из state.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def render_state_variables(
    template: str, 
    context: Dict[str, Any],
    full_state: Dict[str, Any]
) -> str:
    """
    Рендерит шаблон с подстановкой state переменных.
    
    Поддерживаемый синтаксис:
    - {store.warehouse_id} - значение из store
    - {warehouse_id} - значение из store (короткая форма)
    - {user_id} - ID пользователя из state
    - {session_id} - ID сессии из state
    - {?store.warehouse_id} - опциональная подстановка (пустая строка если нет)
    - {?store.warehouse_id|default} - со значением по умолчанию
    - {#messages.count} - количество сообщений (специальная функция)
    
    Args:
        template: Шаблон промпта с плейсхолдерами
        context: Контекст с переменными для подстановки
        full_state: Полный state для специальных функций
        
    Returns:
        Отрендеренный промпт
    """
    result = template
    
    # Паттерн: {опционально?}{путь.к.переменной}{опционально|default}
    # Примеры: {store.id}, {?name}, {?price|0}, {user_id}
    pattern = r'\{(\?)?([a-zA-Z_#][a-zA-Z0-9_\.]*?)(\|([^\}]+))?\}'
    
    def replace_var(match):
        optional = match.group(1) == "?"
        expr = match.group(2)
        default = match.group(4)
        
        # Специальные функции начинаются с #
        if expr.startswith("#"):
            return handle_special_function(expr, full_state, default)
        
        # Обычные переменные: парсим путь (store.warehouse_id -> ["store", "warehouse_id"])
        value = resolve_path(expr, context)
        
        if value is None:
            if optional or default is not None:
                return default or ""
            else:
                # Не нашли переменную и она не опциональная - оставляем как есть
                logger.debug(f"Переменная {expr} не найдена в контексте")
                return match.group(0)
        
        return str(value)
    
    result = re.sub(pattern, replace_var, result)
    return result


def handle_special_function(expr: str, state: Dict[str, Any], default: Optional[str] = None) -> str:
    """
    Обрабатывает специальные функции в промпте.
    
    Поддерживаемые функции:
    - {#messages.count} - количество сообщений
    - {#store.keys} - список ключей в store
    - {#store.empty} - true/false пустой ли store
    
    Args:
        expr: Выражение функции (например "#messages.count")
        state: Полный state
        default: Значение по умолчанию
        
    Returns:
        Результат функции как строка
    """
    if not state:
        return default or ""
    
    if expr == "#messages.count":
        messages = state.get("messages", [])
        return str(len(messages)) if messages else "0"
    
    if expr == "#store.keys":
        store = state.get("store", {})
        if isinstance(store, dict) and store:
            return ", ".join(store.keys())
        return "пусто"
    
    if expr == "#store.empty":
        store = state.get("store", {})
        return "true" if not store else "false"
    
    logger.warning(f"Неизвестная специальная функция: {expr}")
    return default or ""


def resolve_path(path: str, context: Dict[str, Any]) -> Any:
    """
    Резолвит путь к переменной в контексте.
    
    Примеры:
    - "user_id" -> context["user_id"]
    - "store.warehouse_id" -> context["store"]["warehouse_id"]
    - "warehouse_id" -> context["warehouse_id"] (если есть на верхнем уровне)
    
    Args:
        path: Путь к переменной (например "store.warehouse_id")
        context: Контекст с переменными
        
    Returns:
        Значение переменной или None если не найдено
    """
    parts = path.split(".")
    value = context
    
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            return None
            
        if value is None:
            return None
    
    return value

