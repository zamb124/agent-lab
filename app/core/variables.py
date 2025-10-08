"""
Система работы с переменными для промптов и агентов.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.context import get_context

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
        
        # Системные переменные
        if include_system:
            now = datetime.now()
            variables.update({
                "current_date": now.strftime("%Y-%m-%d"),
                "current_time": now.strftime("%H:%M"),
                "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
                "current_year": now.year,
                "current_month": now.month,
                "current_day": now.day,
            })
        
        context = get_context()
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
        safe: bool = True
    ) -> str:
        """
        Рендерит шаблон с подстановкой переменных.
        
        Поддерживаемые форматы:
        - {variable} - простая подстановка
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
            
        variables = VariableResolver.resolve_all(local_vars=local_vars)
        
        result = template
        
        import re
        
        # Подстановка {key.nested} и {key[index]}
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*)\}'
        
        def replace_var(match):
            expr = match.group(1)
            
            try:
                # Парсим выражение: key.nested или key[0]
                value = variables
                parts = re.split(r'\.|\[|\]', expr)
                parts = [p for p in parts if p]
                
                for part in parts:
                    if part.isdigit():
                        value = value[int(part)]
                    else:
                        value = value[part]
                
                return str(value)
            except (KeyError, IndexError, TypeError) as e:
                if safe:
                    return match.group(0)
                else:
                    logger.warning(f"Не удалось резолвить {expr}: {e}")
                    return match.group(0)
        
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
