"""
Декоратор @tool для платформы Humanitec.
Все тулы должны быть async.
"""

import asyncio
import functools
import logging
from typing import Optional, Callable, List, Any

from langchain_core.tools import tool as langchain_tool

from core.variables import set_state_in_context, get_state

logger = logging.getLogger(__name__)


def tool(
    func: Optional[Callable] = None,
    *,
    title: Optional[str] = None,
    group: Optional[str] = None,
    cost: float = 0.0,
    billing_name: Optional[str] = None,
    free_for_plans: Optional[List[str]] = None,
    is_public: bool = False,
    required_permissions: Optional[List[str]] = None,
    max_calls_per_hour: Optional[int] = None,
    state_aware: bool = True,
    name: Optional[str] = None,
    description: Optional[str] = None,
    return_direct: bool = False,
    args_schema: Optional[type] = None,
    infer_schema: bool = True,
):
    """
    Декоратор @tool для платформы Humanitec.
    
    Args:
        title: Название для UI
        group: Группа тулов для UI
        cost: Стоимость вызова в RUB
        billing_name: Название для биллинга
        free_for_plans: Планы для которых бесплатно
        is_public: Доступен ли в публичном редакторе
        state_aware: Автоматически инжектить state из LangGraph
        name: Имя тула для LangChain
        description: Описание тула
        args_schema: Pydantic схема аргументов
    
    Example:
        @tool(title="Погода", group="API")
        async def get_weather(city: str) -> str:
            return f"Погода в {city}: солнечно"
    """

    def decorator(fn: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(fn):
            raise ValueError(f"Tool {fn.__name__} должен быть async функцией")
        
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if state_aware:
                injected_state = kwargs.pop('state', None)
                if injected_state and isinstance(injected_state, dict):
                    set_state_in_context(injected_state)
            
            result = await fn(*args, **kwargs)
            
            if state_aware:
                current_state = get_state()
                if injected_state and current_state:
                    injected_state.update(current_state)
            
            return result

        langchain_kwargs = {
            k: v for k, v in {
                "name": name,
                "description": description,
                "return_direct": return_direct,
                "args_schema": args_schema,
                "infer_schema": infer_schema,
            }.items() if v is not None
        }

        lc_tool = langchain_tool(**langchain_kwargs)(wrapper)

        lc_tool._platform_cost = cost
        lc_tool._platform_billing_name = billing_name or tool_name
        lc_tool._platform_title = title or tool_name
        lc_tool._platform_group = group
        lc_tool._platform_free_for_plans = free_for_plans or []
        lc_tool._platform_is_public = is_public
        lc_tool._platform_required_permissions = required_permissions or []
        lc_tool._platform_max_calls_per_hour = max_calls_per_hour
        lc_tool._is_platform_tool = True

        return lc_tool

    if func is None:
        return decorator
    return decorator(func)
