"""
Расширенный декоратор @tool для платформы Agent Lab.
Заменяет стандартный langchain @tool декоратор с дополнительной функциональностью:
- Биллинг и учет использования
- Контроль доступа по тарифам
- Метаданные для платформы
"""

import functools
from typing import Optional, Callable, Any, Dict, List
from langchain_core.tools import tool as langchain_tool


def tool(
    func: Optional[Callable] = None,
    *,
    # Параметры отображения
    title: Optional[str] = None,          # Название для UI (по умолчанию имя функции)
    
    # Параметры биллинга
    cost: float = 0.0,                    # Стоимость за вызов в RUB
    billing_name: Optional[str] = None,   # Название для биллинга (по умолчанию имя функции)
    free_for_plans: Optional[List[str]] = None, # Для каких планов бесплатно
    
    # Параметры доступа
    is_public: bool = False,                      # Доступен ли тул в публичном редакторе
    required_permissions: Optional[List[str]] = None,  # Требуемые разрешения
    max_calls_per_hour: Optional[int] = None,         # Лимит вызовов в час
    
    # Стандартные параметры langchain tool
    name: Optional[str] = None,
    description: Optional[str] = None,
    return_direct: bool = False,
    args_schema: Optional[type] = None,
    infer_schema: bool = True,
):
    """
    Расширенный декоратор @tool для платформы Agent Lab
    
    Args:
        title: Название для UI (по умолчанию имя функции)
        cost: Стоимость вызова в RUB (0.0 = бесплатно)
        billing_name: Название для биллинга и лимитов (по умолчанию имя функции)
        free_for_plans: Список планов для которых функция бесплатна
        is_public: Доступен ли тул в публичном редакторе (False = только код, True = доступен в UI)
        required_permissions: Список требуемых разрешений
        max_calls_per_hour: Максимум вызовов в час
    
    Examples:
        @tool(is_public=True, title="Погода в городе", cost=0.1, billing_name="weather_api")
        def get_weather(city: str) -> str:
            '''Получить погоду в городе'''
            pass
            
        @tool(is_public=True, title="Калькулятор")
        def calculate(expression: str) -> str:
            '''Вычислить выражение'''
            pass
            
        @tool(is_public=True, title="Премиум функция", cost=1.0, free_for_plans=["premium", "enterprise"])
        def premium_feature() -> str:
            '''Премиум функция'''
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        # Применяем стандартный langchain @tool декоратор
        # Фильтруем None значения
        langchain_kwargs = {}
        if name is not None:
            langchain_kwargs['name'] = name
        if description is not None:
            langchain_kwargs['description'] = description
        langchain_kwargs['return_direct'] = return_direct
        if args_schema is not None:
            langchain_kwargs['args_schema'] = args_schema
        langchain_kwargs['infer_schema'] = infer_schema
        
        langchain_decorated = langchain_tool(**langchain_kwargs)(func)
        
        # Добавляем метаданные платформы к инструменту
        langchain_decorated._platform_title = title or func.__name__
        langchain_decorated._platform_cost = cost
        langchain_decorated._platform_billing_name = billing_name or func.__name__
        langchain_decorated._platform_free_for_plans = free_for_plans or []
        langchain_decorated._platform_is_public = is_public
        langchain_decorated._platform_required_permissions = required_permissions or []
        langchain_decorated._platform_max_calls_per_hour = max_calls_per_hour
        
        # Маркируем как инструмент платформы
        langchain_decorated._is_platform_tool = True
        
        return langchain_decorated
    
    if func is None:
        # Декоратор вызван с параметрами: @tool(cost=0.01)
        return decorator
    else:
        # Декоратор вызван без параметров: @tool
        return decorator(func)
