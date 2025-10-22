"""
Универсальный декоратор @tool для платформы Agent Lab.
Поддерживает использование во всех контекстах: ReAct агент, StateGraph node, Python код.

АРХИТЕКТУРНЫЕ ПРИНЦИПЫ (UnifiedTool подход):
1. Tool работает в трех контекстах одновременно:
   - ReAct агент: обновляет state напрямую через get_state()
   - StateGraph node: возвращает delta для обновления state
   - Python код: возвращает полезный результат через ToolReturn
2. Tool ВСЕГДА возвращает строку для LangGraph (ToolMessage.content)
3. State обновляется автоматически через контекст (get_state/set_state_in_context)
4. Сохраняются все атрибуты платформы (стоимость, title, group и т.д.)
5. НЕ добавляем InjectedToolCallId в схему - это вызывает проблемы с invoke()
"""

import asyncio
import functools
import logging
import inspect
import copy
from typing import Optional, Callable, List, Annotated, Any, Dict
from pydantic import create_model, Field
from dataclasses import dataclass

from langchain_core.tools import tool as langchain_tool
from langgraph.errors import GraphInterrupt
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from langchain_core.messages import ToolMessage

from app.core.variables import set_state_in_context, get_state
from app.core.context import get_context

logger = logging.getLogger(__name__)


@dataclass
class ToolReturn:
    """Универсальный возврат от tool с delta для state и result для кода"""
    delta: Dict[str, Any]        # дельта к AppState
    result: Any                  # полезный результат «для кода»


def tool(
    func: Optional[Callable] = None,
    *,
    # Параметры отображения
    title: Optional[str] = None,          # Название для UI (по умолчанию имя функции)
    group: Optional[str] = None,          # Группа тулов для UI группировки

    # Параметры биллинга
    cost: float = 0.0,                    # Стоимость за вызов в RUB
    billing_name: Optional[str] = None,   # Название для биллинга (по умолчанию имя функции)
    free_for_plans: Optional[List[str]] = None, # Для каких планов бесплатно

    # Параметры доступа
    is_public: bool = False,                      # Доступен ли тул в публичном редакторе
    required_permissions: Optional[List[str]] = None,  # Требуемые разрешения
    max_calls_per_hour: Optional[int] = None,         # Лимит вызовов в час

    # Параметры state
    state_aware: bool = True,                         # Автоматически инжектить state из графа

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
        group: Группа тулов для UI группировки (например, "Коммуникации", "Анализ данных")
        cost: Стоимость вызова в RUB (0.0 = бесплатно)
        billing_name: Название для биллинга и лимитов (по умолчанию имя функции)
        free_for_plans: Список планов для которых функция бесплатна
        is_public: Доступен ли тул в публичном редакторе
        required_permissions: Список требуемых разрешений
        max_calls_per_hour: Максимум вызовов в час
        state_aware: Автоматически инжектить state из LangGraph (по умолчанию True для всех тулов)

    Examples:
        # Обычный tool (автоматически оборачивается в ToolReturn)
        @tool(is_public=True, group="Погода", title="Погода")
        def get_weather(city: str) -> str:
            return f"Погода в {city}: солнечно"
        # Декоратор автоматически оборачивает в ToolReturn(delta={}, result="...")
        # ВЕЗДЕ возвращается ToolReturn: result = tool.invoke({"city": "Москва"}) -> ToolReturn(delta={}, result="Погода в Москва: солнечно")

        # Универсальный tool с явным ToolReturn
        @tool(is_public=True, state_aware=True, title="Сохранить в сессию")
        def session_set(key: str, value: str) -> ToolReturn:
            state = get_state()  # Актуальный state благодаря state_aware=True
            state["store"][key] = value
            
            return ToolReturn(
                delta={"store": state["store"]},  # Для LangGraph
                result=f"Сохранено: {key} = {value}"  # Для Python кода
            )

        # Tool, изменяющий state напрямую (автоматически детектируется)
        @tool(state_aware=True)
        def create_task(message: str) -> str:
            state = get_state()
            state["tasks"] = state.get("tasks", []) + [message]
            return f"Задача создана: {message}"
        # Декоратор автоматически детектирует изменения state и обновляет delta
        # ВЕЗДЕ возвращается ToolReturn: result = tool.invoke({"message": "test"}) -> ToolReturn(delta={"tasks": [...]}, result="Задача создана: test")
    """
    
    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)
        tool_name = name or func.__name__
        
        # Создаем wrapper функцию для универсального использования
        if is_async:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Обработка state для LangGraph
                injected_state = None
                
                if state_aware:
                    # Извлекаем state если он передан (из LangGraph)
                    injected_state = kwargs.pop('state', None)
                    logger.debug(f"🔍 [{tool_name}] state_aware=True, injected_state={injected_state is not None}")
                    
                    if injected_state and isinstance(injected_state, dict):
                        # Устанавливаем state в контекст для доступа через get_state()
                        set_state_in_context(injected_state)
                        logger.debug(f"🔄 State установлен в контекст для {tool_name}")
                    else:
                        logger.debug(f"⚠️ [{tool_name}] injected_state не передан или не dict: {injected_state}")
                        injected_state = None
                
                try:
                    # Вызываем оригинальную функцию
                    tool_result = await func(*args, **kwargs)
                    
                    # Определяем контекст выполнения
                    context = get_context()
                    agent_type = None
                    if context and hasattr(context, 'agent_config') and context.agent_config:
                        agent_type = context.agent_config.type
                    
                    logger.info(f"🔍 [{tool_name}] Контекст: injected_state={'есть' if injected_state else 'нет'}, agent_type={agent_type}")
                    
                    # ВСЕГДА оборачиваем результат в ToolReturn для единообразия
                    if isinstance(tool_result, ToolReturn):
                        # Если уже ToolReturn - используем как есть
                        wrapped_result = tool_result
                    else:
                        # Если обычный результат - оборачиваем в ToolReturn
                        wrapped_result = ToolReturn(
                            delta={},  # Пустая дельта для обычных результатов
                            result=tool_result
                        )
                    
                    # Простая логика: если есть injected_state, обновляем его напрямую
                    if injected_state is not None:
                        # Получаем текущий state после выполнения функции
                        current_state = get_state()
                        if current_state:
                            # Обновляем injected_state напрямую
                            for key, value in current_state.items():
                                injected_state[key] = value
                            logger.info(f"✅ [{tool_name}] injected_state обновлен: {list(current_state.keys())}")
                            
                            # Для StateGraph агентов также заполняем delta
                            if agent_type == "stategraph":
                                wrapped_result.delta = current_state
                                logger.info(f"🔄 [{tool_name}] StateGraph delta заполнен: {list(current_state.keys())}")
                    
                    # Возвращаем результат в зависимости от контекста
                    if injected_state is not None:
                        # В LangGraph - определяем тип агента
                        if agent_type == "stategraph":
                            # В StateGraph агенте - возвращаем delta для обновления state
                            logger.info(f"🔄 [{tool_name}] StateGraph агент - возвращаем delta: {wrapped_result.delta}")
                            return wrapped_result.delta
                        else:
                            # В ReAct агенте - возвращаем строку для ToolMessage.content
                            # State будет обновлен вручную после ainvoke через checkpointer
                            logger.info(f"🔄 [{tool_name}] ReAct агент - возвращаем строку: {wrapped_result.result}")
                            if isinstance(wrapped_result.result, str):
                                return wrapped_result.result
                            else:
                                return str(wrapped_result.result)
                    else:
                        # В обычном Python коде - возвращаем только result
                        logger.info(f"🔄 [{tool_name}] Python код - возвращаем result: {wrapped_result.result}")
                        return wrapped_result.result
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в tool {tool_name}: {e}", exc_info=True)
                    raise
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Обработка state для LangGraph
                injected_state = None
                
                if state_aware:
                    # Извлекаем state если он передан (из LangGraph)
                    injected_state = kwargs.pop('state', None)
                    logger.debug(f"🔍 [{tool_name}] state_aware=True, injected_state={injected_state is not None}")
                    
                    if injected_state and isinstance(injected_state, dict):
                        # Устанавливаем state в контекст для доступа через get_state()
                        set_state_in_context(injected_state)
                        logger.debug(f"🔄 State установлен в контекст для {tool_name}")
                    else:
                        logger.debug(f"⚠️ [{tool_name}] injected_state не передан или не dict: {injected_state}")
                        injected_state = None
                
                try:
                    # Вызываем оригинальную функцию
                    tool_result = func(*args, **kwargs)
                    
                    # Определяем контекст выполнения
                    context = get_context()
                    agent_type = None
                    if context and hasattr(context, 'agent_config') and context.agent_config:
                        agent_type = context.agent_config.type
                    
                    logger.info(f"🔍 [{tool_name}] Контекст: injected_state={'есть' if injected_state else 'нет'}, agent_type={agent_type}")
                    
                    # ВСЕГДА оборачиваем результат в ToolReturn для единообразия
                    if isinstance(tool_result, ToolReturn):
                        # Если уже ToolReturn - используем как есть
                        wrapped_result = tool_result
                    else:
                        # Если обычный результат - оборачиваем в ToolReturn
                        wrapped_result = ToolReturn(
                            delta={},  # Пустая дельта для обычных результатов
                            result=tool_result
                        )
                    
                    # Простая логика: если есть injected_state, обновляем его напрямую
                    if injected_state is not None:
                        # Получаем текущий state после выполнения функции
                        current_state = get_state()
                        if current_state:
                            # Обновляем injected_state напрямую
                            for key, value in current_state.items():
                                injected_state[key] = value
                            logger.info(f"✅ [{tool_name}] injected_state обновлен: {list(current_state.keys())}")
                            
                            # Для StateGraph агентов также заполняем delta
                            if agent_type == "stategraph":
                                wrapped_result.delta = current_state
                                logger.info(f"🔄 [{tool_name}] StateGraph delta заполнен: {list(current_state.keys())}")
                    
                    # Возвращаем результат в зависимости от контекста
                    if injected_state is not None:
                        # В LangGraph - определяем тип агента
                        if agent_type == "stategraph":
                            # В StateGraph агенте - возвращаем delta для обновления state
                            logger.info(f"🔄 [{tool_name}] StateGraph агент - возвращаем delta: {wrapped_result.delta}")
                            return wrapped_result.delta
                        else:
                            # В ReAct агенте - возвращаем строку для ToolMessage.content
                            # State будет обновлен вручную после ainvoke через checkpointer
                            logger.info(f"🔄 [{tool_name}] ReAct агент - возвращаем строку: {wrapped_result.result}")
                            if isinstance(wrapped_result.result, str):
                                return wrapped_result.result
                            else:
                                return str(wrapped_result.result)
                    else:
                        # В обычном Python коде - возвращаем только result
                        logger.info(f"🔄 [{tool_name}] Python код - возвращаем result: {wrapped_result.result}")
                        return wrapped_result.result
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка в tool {tool_name}: {e}", exc_info=True)
                    raise
        
        # Применяем стандартный langchain декоратор
        langchain_kwargs = {
            "name": name,
            "description": description,
            "return_direct": return_direct,
            "args_schema": args_schema,
            "infer_schema": infer_schema,
        }
        
        # Убираем None значения
        langchain_kwargs = {k: v for k, v in langchain_kwargs.items() if v is not None}
        
        langchain_decorated = langchain_tool(**langchain_kwargs)(wrapper)
        
        # Добавляем поддержку state если нужно
        if state_aware:
            # Получаем оригинальную схему
            original_schema = langchain_decorated.args_schema
            
            if original_schema:
                # Создаем новую схему с дополнительными полями
                field_definitions = {}
                
                # Копируем все поля из оригинальной схемы, но без Annotated типов
                for field_name, field_info in original_schema.model_fields.items():
                    # Извлекаем базовый тип из Annotated если есть
                    annotation = field_info.annotation
                    if hasattr(annotation, '__origin__') and annotation.__origin__ is Annotated:
                        # Если это Annotated[BaseType, ...], берем BaseType
                        annotation = annotation.__args__[0]
                    
                    field_definitions[field_name] = (
                        annotation,
                        Field(
                            default=field_info.default,
                            description=field_info.description,
                            **{k: v for k, v in field_info.json_schema_extra.items() if k not in ['default', 'description']} if field_info.json_schema_extra else {}
                        )
                    )
                
                # Добавляем только state поле с InjectedState (БЕЗ tool_call_id!)
                field_definitions['state'] = (
                    Annotated[Optional[Dict[str, Any]], InjectedState],
                    Field(default=None, description="State из LangGraph (автоматически инжектируется)")
                )
                
                # Создаем новую схему
                logger.debug(f"🔍 Создаем схему {original_schema.__name__}WithState с полями: {list(field_definitions.keys())}")
                try:
                    new_schema = create_model(
                        f"{original_schema.__name__}WithState",
                        **field_definitions
                    )
                    logger.debug(f"✅ Схема создана успешно")
                except Exception as e:
                    logger.error(f"❌ Ошибка создания схемы: {e}")
                    logger.error(f"❌ Поля: {field_definitions}")
                    raise
                
                # Заменяем схему
                langchain_decorated.args_schema = new_schema
        
        # Добавляем метаданные платформы
        langchain_decorated._platform_cost = cost
        langchain_decorated._platform_billing_name = billing_name or tool_name
        langchain_decorated._platform_title = title or tool_name
        langchain_decorated._platform_group = group
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