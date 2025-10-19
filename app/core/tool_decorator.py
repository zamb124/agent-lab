"""
Расширенный декоратор @tool для платформы Agent Lab.
Заменяет стандартный langchain @tool декоратор с дополнительной функциональностью:
- Биллинг и учет использования
- Контроль доступа по тарифам
- Метаданные для платформы
"""

import asyncio
import functools
import logging
from typing import Optional, Callable, List
from langchain_core.tools import tool as langchain_tool
from langgraph.errors import GraphInterrupt

logger = logging.getLogger(__name__)


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
    
    # Параметры state
    state_aware: bool = False,                        # Автоматически инжектить state из графа
    
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
        is_public: Доступен ли тул в публичном редакторе
        required_permissions: Список требуемых разрешений
        max_calls_per_hour: Максимум вызовов в час
        state_aware: Автоматически инжектить state из LangGraph (по умолчанию True для всех тулов)
    
    Examples:
        @tool(is_public=True, title="Погода")
        def get_weather(city: str) -> str:
            pass
            
        @tool(is_public=True, state_aware=True, title="Сохранить в сессию")
        def session_set(key: str, value: str) -> str:
            state = get_state()  # Актуальный state благодаря state_aware=True
            state["store"][key] = value
    """
    
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                tool_name = name or func.__name__
                logger.info(f"🔧 [TOOL START] {tool_name}")
                logger.info(f"   Args: {args}")
                logger.info(f"   Kwargs: {kwargs}")
                
                
                # Если state_aware=True, извлекаем state и tool_call_id
                state_before = None
                injected_tool_call_id = None
                
                if state_aware:
                    from app.core.variables import set_state_in_context
                    import copy
                    
                    # Извлекаем state и устанавливаем в context
                    injected_state = kwargs.pop('state', None)
                    
                    if injected_state and isinstance(injected_state, dict):
                        # Сохраняем копию state ДО вызова тула для сравнения
                        state_before = copy.deepcopy(injected_state.get('store', {}))
                        
                        set_state_in_context(injected_state)
                        logger.debug(f"🔄 State инжектирован в context для {tool_name}")
                    
                    # Извлекаем tool_call_id
                    injected_tool_call_id = kwargs.pop('tool_call_id', None)
                    if injected_tool_call_id:
                        # Добавляем обратно если функция ожидает tool_call_id
                        import inspect
                        sig = inspect.signature(func)
                        if 'tool_call_id' in sig.parameters:
                            kwargs['tool_call_id'] = injected_tool_call_id
                
                try:
                    result = await func(*args, **kwargs)
                    logger.info(f"✅ [TOOL SUCCESS] {tool_name}")
                    logger.info(f"   Result type: {type(result)}")
                    
                    # Если state_aware=True и state изменился, оборачиваем в Command
                    if state_aware and state_before is not None:
                        from app.core.context import get_context
                        from langgraph.types import Command
                        from langchain_core.messages import ToolMessage
                        
                        context_after = get_context()
                        if context_after and context_after.state:
                            state_after = context_after.state.get('store', {})
                            
                            # Сравниваем state до и после
                            if state_after != state_before:
                                logger.info(f"🔄 [{tool_name}] State изменился, возвращаем Command")
                                
                                # Если тул уже вернул Command - возвращаем как есть
                                if isinstance(result, Command):
                                    return result
                                
                                # Иначе оборачиваем результат в Command
                                result_text = str(result) if not isinstance(result, str) else result
                                
                                return Command(update={
                                    "store": state_after,
                                    "messages": [ToolMessage(result_text, tool_call_id=injected_tool_call_id or "unknown")]
                                })
                    
                    return result
                except Exception as e:
                    if isinstance(e, GraphInterrupt):
                        logger.info(f"💬 [TOOL ASK_USER] {tool_name}: запрос данных у пользователя")
                        raise
                    else:
                        logger.error(f"❌ [TOOL ERROR] {tool_name}: {e}", exc_info=True)
                        raise
            
            wrapped_func = async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                tool_name = name or func.__name__
                logger.info(f"🔧 [TOOL START] {tool_name}")
                logger.info(f"   Args: {args}")
                logger.info(f"   Kwargs: {kwargs}")
                
                # Если state_aware=True, извлекаем state и tool_call_id
                state_before = None
                injected_tool_call_id = None
                
                if state_aware:
                    from app.core.variables import set_state_in_context
                    import copy
                    
                    # Извлекаем state и устанавливаем в context
                    injected_state = kwargs.pop('state', None)
                    
                    if injected_state and isinstance(injected_state, dict):
                        # Сохраняем копию state ДО вызова тула
                        state_before = copy.deepcopy(injected_state.get('store', {}))
                        
                        set_state_in_context(injected_state)
                        logger.debug(f"🔄 State инжектирован в context для {tool_name}")
                    
                    # Извлекаем tool_call_id
                    injected_tool_call_id = kwargs.pop('tool_call_id', None)
                    if injected_tool_call_id:
                        import inspect
                        sig = inspect.signature(func)
                        if 'tool_call_id' in sig.parameters:
                            kwargs['tool_call_id'] = injected_tool_call_id
                
                try:
                    result = func(*args, **kwargs)
                    logger.info(f"✅ [TOOL SUCCESS] {tool_name}")
                    logger.info(f"   Result type: {type(result)}")
                    
                    # Если state_aware=True и state изменился, оборачиваем в Command
                    if state_aware and state_before is not None:
                        from app.core.context import get_context
                        from langgraph.types import Command
                        from langchain_core.messages import ToolMessage
                        
                        context_after = get_context()
                        if context_after and context_after.state:
                            state_after = context_after.state.get('store', {})
                            
                            if state_after != state_before:
                                logger.info(f"🔄 [{tool_name}] State изменился, возвращаем Command")
                                
                                if isinstance(result, Command):
                                    return result
                                
                                result_text = str(result) if not isinstance(result, str) else result
                                
                                return Command(update={
                                    "store": state_after,
                                    "messages": [ToolMessage(result_text, tool_call_id=injected_tool_call_id or "unknown")]
                                })
                    
                    return result
                except Exception as e:
                    if isinstance(e, GraphInterrupt):
                        logger.info(f"💬 [TOOL ASK_USER] {tool_name}: запрос данных у пользователя")
                        raise
                    else:
                        logger.error(f"❌ [TOOL ERROR] {tool_name}: {e}", exc_info=True)
                        raise
            
            wrapped_func = sync_wrapper
        
        # Применяем стандартный langchain @tool декоратор к обернутой функции
        langchain_kwargs = {}
        if name is not None:
            langchain_kwargs['name'] = name
        if description is not None:
            langchain_kwargs['description'] = description
        langchain_kwargs['return_direct'] = return_direct
        if args_schema is not None:
            langchain_kwargs['args_schema'] = args_schema
        langchain_kwargs['infer_schema'] = infer_schema
        
        langchain_decorated = langchain_tool(**langchain_kwargs)(wrapped_func)
        
        # ПОСЛЕ langchain декоратора добавляем state и tool_call_id параметры
        if state_aware:
            from typing import Annotated
            from langgraph.prebuilt import InjectedState
            from langchain_core.tools import InjectedToolCallId
            from pydantic import create_model, Field
            
            # Создаем новую схему с дополнительными полями
            if hasattr(langchain_decorated, 'args_schema') and langchain_decorated.args_schema:
                original_schema = langchain_decorated.args_schema
                
                # Получаем поля из оригинальной схемы
                if hasattr(original_schema, 'model_fields'):
                    original_fields = original_schema.model_fields
                elif hasattr(original_schema, '__fields__'):
                    original_fields = original_schema.__fields__
                else:
                    original_fields = {}
                
                # Создаем dict для create_model
                field_definitions = {}
                for field_name, field_info in original_fields.items():
                    field_definitions[field_name] = (field_info.annotation, field_info)
                
                # Добавляем state и tool_call_id поля
                field_definitions['state'] = (
                    Annotated[dict, InjectedState],
                    Field(default=None)
                )
                field_definitions['tool_call_id'] = (
                    Annotated[str, InjectedToolCallId],
                    Field(default=None)
                )
                
                # Создаем новую схему
                new_schema = create_model(
                    original_schema.__name__,
                    **field_definitions
                )
                
                # Заменяем схему
                langchain_decorated.args_schema = new_schema
                
                logger.debug(f"✅ [POST-LANGCHAIN] Добавлены state и tool_call_id в схему {func.__name__}")
        
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
