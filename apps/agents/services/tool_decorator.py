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
import json
from typing import Optional, Callable, List, Annotated, Any, Dict
from pydantic import create_model, Field
from dataclasses import dataclass

from opentelemetry import trace
from langchain_core.tools import tool as langchain_tool
from apps.agents.agents.base import AgentInterrupt
from langchain_core.messages import ToolMessage

from core.variables import set_state_in_context, get_state
from core.context import get_context
from apps.agents.models.trace_models import SpanType

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

        # Получаем tracer для трейсинга
        tracer = trace.get_tracer("agent-lab.tool_decorator")

        # Создаем wrapper функцию для универсального использования
        if is_async:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Создаем span для трейсинга
                span_name = f"tool.{tool_name}"
                with tracer.start_as_current_span(span_name) as span:
                    # Базовые атрибуты
                    span.set_attribute("span_type", SpanType.TOOL.value)
                    span.set_attribute("tool_name", tool_name)

                    # Метаданные tool
                    if title:
                        span.set_attribute("meta_title", title)
                    if billing_name:
                        span.set_attribute("meta_billing_name", billing_name)
                    if group:
                        span.set_attribute("meta_group", group)
                    if cost > 0:
                        span.set_attribute("meta_cost", cost)

                    # Контекст (если доступен)
                    context = get_context()
                    if context and context.user:
                        span.set_attribute("context_user_id", context.user.user_id)
                    if context and context.active_company:
                        span.set_attribute("context_company_id", context.active_company.company_id)
                    if context and context.session_id:
                        span.set_attribute("context_session_id", context.session_id)

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

                    # Подготовка input_data для трейсинга (без state, чтобы не перегружать)
                    input_data = {"args": [str(arg) for arg in args], "kwargs": {k: str(v) for k, v in kwargs.items() if k != 'state'}}
                    span.set_attribute("input_data", json.dumps(input_data))

                    try:
                        # Вызываем оригинальную функцию
                        tool_result = await func(*args, **kwargs)

                        # Определяем контекст выполнения
                        context = get_context()
                        agent_type = None
                        agent_type_str = None
                        if context and hasattr(context, 'agent_config') and context.agent_config:
                            agent_type = context.agent_config.type
                            if hasattr(agent_type, 'value'):
                                agent_type_str = agent_type.value
                            else:
                                agent_type_str = str(agent_type)

                        logger.info(f"🔍 [{tool_name}] Контекст: injected_state={'есть' if injected_state else 'нет'}, agent_type={agent_type_str}")

                        # ВСЕГДА оборачиваем результат в ToolReturn для единообразия
                        if isinstance(tool_result, ToolReturn):
                            wrapped_result = tool_result
                        else:
                            wrapped_result = ToolReturn(
                                delta={},
                                result=tool_result
                            )

                        # Получаем текущий state после выполнения функции
                        current_state = get_state()
                        
                        # Если есть injected_state, обновляем его напрямую
                        if injected_state is not None and current_state:
                            for key, value in current_state.items():
                                injected_state[key] = value
                            logger.info(f"✅ [{tool_name}] injected_state обновлен: {list(current_state.keys())}")

                        # Для StateGraph агентов заполняем delta из current_state
                        if agent_type_str == "stategraph" and current_state:
                            wrapped_result.delta = current_state
                            logger.info(f"🔄 [{tool_name}] StateGraph delta заполнен: {list(current_state.keys())}")

                        # Записываем output_data в span
                        output_data = {
                            "result": str(wrapped_result.result)[:500],
                            "has_delta": bool(wrapped_result.delta),
                            "agent_type": agent_type_str or "none"
                        }
                        span.set_attribute("output_data", json.dumps(output_data))

                        # Возвращаем результат в зависимости от контекста
                        if agent_type_str == "stategraph":
                            return wrapped_result.delta if wrapped_result.delta else wrapped_result.result
                        elif injected_state is not None:
                            if isinstance(wrapped_result.result, str):
                                return wrapped_result.result
                            else:
                                return str(wrapped_result.result)
                        else:
                            return wrapped_result.result

                    except Exception as e:
                        # Записываем исключение в span
                        span.record_exception(e)
                        logger.error(f"❌ Ошибка в tool {tool_name}: {e}", exc_info=True)
                        raise
        else:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Создаем span для трейсинга
                span_name = f"tool.{tool_name}"
                with tracer.start_as_current_span(span_name) as span:
                    # Базовые атрибуты
                    span.set_attribute("span_type", SpanType.TOOL.value)
                    span.set_attribute("tool_name", tool_name)

                    # Метаданные tool
                    if title:
                        span.set_attribute("meta_title", title)
                    if billing_name:
                        span.set_attribute("meta_billing_name", billing_name)
                    if group:
                        span.set_attribute("meta_group", group)
                    if cost > 0:
                        span.set_attribute("meta_cost", cost)

                    # Контекст (если доступен)
                    context = get_context()
                    if context and context.user:
                        span.set_attribute("context_user_id", context.user.user_id)
                    if context and context.active_company:
                        span.set_attribute("context_company_id", context.active_company.company_id)
                    if context and context.session_id:
                        span.set_attribute("context_session_id", context.session_id)

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

                    # Подготовка input_data для трейсинга (без state, чтобы не перегружать)
                    input_data = {"args": [str(arg) for arg in args], "kwargs": {k: str(v) for k, v in kwargs.items() if k != 'state'}}
                    span.set_attribute("input_data", json.dumps(input_data))

                    try:
                        # Вызываем оригинальную функцию
                        tool_result = func(*args, **kwargs)

                        # Определяем контекст выполнения
                        context = get_context()
                        agent_type = None
                        agent_type_str = None
                        if context and hasattr(context, 'agent_config') and context.agent_config:
                            agent_type = context.agent_config.type
                            if hasattr(agent_type, 'value'):
                                agent_type_str = agent_type.value
                            else:
                                agent_type_str = str(agent_type)

                        logger.info(f"🔍 [{tool_name}] Контекст: injected_state={'есть' if injected_state else 'нет'}, agent_type={agent_type_str}")

                        # ВСЕГДА оборачиваем результат в ToolReturn для единообразия
                        if isinstance(tool_result, ToolReturn):
                            wrapped_result = tool_result
                        else:
                            wrapped_result = ToolReturn(
                                delta={},
                                result=tool_result
                            )

                        # Получаем текущий state после выполнения функции
                        current_state = get_state()
                        
                        # Если есть injected_state, обновляем его напрямую
                        if injected_state is not None and current_state:
                            for key, value in current_state.items():
                                injected_state[key] = value
                            logger.info(f"✅ [{tool_name}] injected_state обновлен: {list(current_state.keys())}")

                        # Для StateGraph агентов заполняем delta из current_state
                        if agent_type_str == "stategraph" and current_state:
                            wrapped_result.delta = current_state
                            logger.info(f"🔄 [{tool_name}] StateGraph delta заполнен: {list(current_state.keys())}")

                        # Записываем output_data в span
                        output_data = {
                            "result": str(wrapped_result.result)[:500],
                            "has_delta": bool(wrapped_result.delta),
                            "agent_type": agent_type_str or "none"
                        }
                        span.set_attribute("output_data", json.dumps(output_data))

                        # Возвращаем результат в зависимости от контекста
                        if agent_type_str == "stategraph":
                            return wrapped_result.delta if wrapped_result.delta else wrapped_result.result
                        elif injected_state is not None:
                            if isinstance(wrapped_result.result, str):
                                return wrapped_result.result
                            else:
                                return str(wrapped_result.result)
                        else:
                            return wrapped_result.result

                    except Exception as e:
                        # Записываем исключение в span
                        span.record_exception(e)
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

                # НЕ добавляем state в args_schema - он не должен попадать в LLM
                # State устанавливается в контекст через set_state_in_context() и доступен через get_state()

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