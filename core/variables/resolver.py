"""
Система работы с переменными для промптов и агентов.
"""

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from core.context import get_context

logger = logging.getLogger(__name__)


class VariableResolver:
    """
    Резолвер переменных с приоритетами.
    
    Приоритет (от высшего к низшему):
    1. Локальные переменные агента (передаются явно)
    2. Переменные flow
    3. Переменные компании
    4. Системные переменные
    """
    
    @staticmethod
    def resolve_all(
        local_vars: Optional[Dict[str, Any]] = None,
        include_system: bool = True
    ) -> Dict[str, Any]:
        """
        Собирает все переменные с учетом приоритета.
        
        Args:
            local_vars: Локальные переменные (наивысший приоритет)
            include_system: Включать ли системные переменные (дата, время)
            
        Returns:
            Словарь всех переменных
        """
        variables = {}
        
        context = get_context()
        
        # Системные переменные (с учётом таймзоны из state.store.timezone если есть)
        if include_system:
            tz = None
            if context and getattr(context, "state", None):
                store = context.state.get("store", {}) if isinstance(context.state, dict) else {}
                tz_name = store.get("timezone") if isinstance(store, dict) else None
                if tz_name:
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        tz = None
            now = datetime.now(tz) if tz else datetime.now()
            variables.update({
                "current_date": now.strftime("%Y-%m-%d"),
                "current_time": now.strftime("%H:%M"),
                "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "current_year": now.year,
                "current_month": now.month,
                "current_day": now.day,
            })
        if not context:
            logger.warning("Нет контекста при резолвинге переменных")
            if local_vars:
                variables.update(local_vars)
            return variables
        
        # Переменные компании
        if context.active_company:
            variables.update({
                "company_name": context.active_company.name,
                "company_id": context.active_company.company_id,
                "company_subdomain": context.active_company.subdomain,
            })
            
            if context.company_variables:
                variables.update(context.company_variables)
        
        # Переменные пользователя
        if context.user:
            variables.update({
                "user_name": context.user.name,
                "user_id": context.user.user_id,
            })
        
        # Переменные flow
        if context.flow_variables:
            variables.update(context.flow_variables)
        
        # Локальные переменные (наивысший приоритет)
        if local_vars:
            variables.update(local_vars)
        
        return variables
    
    @staticmethod
    def render_template(
        template: str,
        local_vars: Optional[Dict[str, Any]] = None,
        safe: bool = True,
        include_system: bool = True,
    ) -> str:
        """
        Рендерит шаблон с подстановкой переменных.
        
        Поддерживаемые форматы:
        - {variable} - простая подстановка
        - {?variable} - опциональная (пустая строка если нет)
        - {?variable|default} - опциональная со значением по умолчанию
        - {dict.key} - доступ к вложенным dict
        - {list[0]} - доступ к элементам list
        - {{variable}} - двойные скобки (Jinja-style)
        
        Args:
            template: Шаблон строки
            local_vars: Локальные переменные для подстановки
            safe: Если True, не падает на отсутствующие переменные
            
        Returns:
            Строка с подставленными переменными
        """
        if not template:
            return template
            
        variables = VariableResolver.resolve_all(local_vars=local_vars, include_system=include_system)
        
        result = template
        
        # Паттерн с поддержкой опциональности и дефолтов
        # {?variable|default} или {variable} или {dict.key[0]}
        pattern = r'\{(\?)?([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*?)(\|([^\}]+))?\}'
        
        def replace_var(match):
            optional = match.group(1) == "?"
            expr = match.group(2)
            default = match.group(4)
            
            value = variables
            parts = re.split(r'\.|\[|\]', expr)
            parts = [p for p in parts if p]
            
            found = True
            for part in parts:
                if part.isdigit():
                    if isinstance(value, (list, tuple)) and int(part) < len(value):
                        value = value[int(part)]
                    else:
                        found = False
                        break
                else:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        found = False
                        break
            
            if not found:
                if optional or default is not None:
                    return default or ""
                elif safe:
                    return match.group(0)
                else:
                    logger.warning(f"Не удалось резолвить {expr}")
                    return match.group(0)
            
            return str(value)
        
        result = re.sub(pattern, replace_var, result)
        
        # Подстановка {{variable}} (двойные скобки)
        pattern_double = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*)\}\}'
        result = re.sub(pattern_double, replace_var, result)
        
        return result


def get_state() -> Optional[Dict[str, Any]]:
    """
    Получает state агента из контекста.
    Используется в тулах для доступа к store и другим данным state.
    
    Returns:
        State агента или None если не доступен
    """
    context = get_context()
    if context is None:
        return None
    return context.state


def set_state_in_context(state: Dict[str, Any]) -> None:
    """
    Устанавливает state в контекст.
    Вызывается автоматически при входе в агента.
    
    Args:
        state: State агента для установки в контекст
    """
    context = get_context()
    context.state = state
