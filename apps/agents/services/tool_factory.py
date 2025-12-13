"""
Фабрика для создания инструментов на основе конфигурации.
"""

import logging
import importlib
import inspect
import functools
import asyncio
import re
import typing
import json
from typing import List, Any, Dict
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field, create_model

from apps.agents.models import ToolReference, CodeMode
from core.models.context_models import Context
from apps.agents.container import get_agents_container
from core.context import get_context
from core.variables import get_state
from apps.agents.services.progress_sender import send_progress
from apps.agents.tools.session.session_tools import (
    session_set, session_get, session_has, session_delete, session_keys, get_variable
)
from apps.agents.tools.misc.standard import ask_user
from apps.agents.services.tool_decorator import tool
from apps.agents.exceptions import AgentInterrupt
from core.billing import BillingService
from core.models.billing_models import UsageType
from apps.agents.services.mcp_client import get_mcp_client, format_mcp_result

def interrupt(message: str):
    """Функция для прерывания выполнения с запросом ввода от пользователя"""
    raise AgentInterrupt(message)

logger = logging.getLogger(__name__)


class ToolFactory:
    """Фабрика для создания инструментов"""

    def __init__(self):
        self._module_cache = {}

    def _normalize_module_path(self, module_path: str) -> str:
        """
        Нормализует путь модуля из старого формата app.* в apps.*
        """
        if module_path.startswith("app."):
            normalized = "apps.agents." + module_path[4:]
            logger.warning(f"Нормализация пути модуля: {module_path} → {normalized}")
            return normalized
        return module_path

    def _get_cached_module(self, module_path: str, reload: bool = False):
        """
        Получает модуль с кэшированием.

        Args:
            module_path: Путь к модулю
            reload: Принудительно перезагрузить модуль

        Returns:
            Загруженный модуль
        """
        module_path = self._normalize_module_path(module_path)

        if reload or module_path not in self._module_cache:
            module = importlib.import_module(module_path)
            if reload and module_path in self._module_cache:
                module = importlib.reload(module)
            self._module_cache[module_path] = module
            logger.debug(f"Модуль загружен и кэширован: {module_path}")
        else:
            logger.debug(f"Модуль взят из кэша: {module_path}")

        return self._module_cache[module_path]

    def clear_cache(self):
        """Очищает кэш загруженных modules и tools"""
        self._tool_cache.clear()
        self._module_cache.clear()
        logger.info("Кэш ToolFactory очищен")

    async def create_tools(self, tool_refs: List[ToolReference]) -> List[Any]:
        """Создает инструменты по списку ToolReference"""
        return [await self._create_single_tool(ref) for ref in tool_refs]

    async def _create_single_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент по ссылке. Тип определяется через code_mode."""
        match ref.code_mode:
            case CodeMode.MCP_TOOL:
                tool = await self._create_mcp_tool(ref)
            case CodeMode.AGENT_TOOL:
                tool = await self._create_agent_tool(ref)
            case CodeMode.FLOW_TOOL:
                tool = await self._create_flow_tool(ref)
            case CodeMode.INLINE_CODE:
                tool = await self._create_inline_code_tool(ref)
            case CodeMode.CODE_REFERENCE:
                tool = await self._create_function_tool(ref)
            case _:
                raise ValueError(f"Неизвестный code_mode: {ref.code_mode}")

        if ref.cost > 0 or ref.tariff_limits or ref.free_for_plans:
            tool = self._wrap_tool_with_billing(tool, ref)

        return tool

    async def _create_inline_code_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из inline кода"""
        if not ref.inline_code:
            raise ValueError(f"INLINE_CODE инструмент {ref.tool_id} не содержит inline_code")

        logger.debug(f"🔥 Создаем INLINE_CODE инструмент: {ref.tool_id}")
        logger.debug(f"🔥 Inline код: {ref.inline_code[:100]}...")

        # Создаем namespace для выполнения кода с необходимыми импортами
        # Используем тот же namespace, что и для документации
        namespace = await self.get_tool_namespace()

        # Проверяем есть ли уже @tool декоратор в коде
        has_tool_decorator = '@tool' in ref.inline_code

        # Если нет @tool декоратора, добавляем его автоматически
        if not has_tool_decorator:
            logger.debug("@tool декоратор не найден, добавляем автоматически")

            # Конвертируем def в async def если нужно
            code_body = ref.inline_code.strip()
            if 'async def ' not in code_body and 'def ' in code_body:
                code_body = code_body.replace('def ', 'async def ', 1)

            enhanced_code = f'''
from apps.agents.services.tool_decorator import tool

@tool
{code_body}
'''
            logger.debug(f"Улучшенный код: {enhanced_code[:200]}...")
            exec(enhanced_code, namespace, namespace)
        else:
            logger.debug("@tool декоратор уже есть в коде")
            exec(ref.inline_code, namespace, namespace)

        # Ищем функцию main или первую функцию через регулярку
        tool_function = namespace.get('main')
        if not tool_function:
            # Ищем первую функцию через регулярные выражения
            # Паттерн для поиска def или async def функций
            function_pattern = r'^(async\s+)?def\s+(\w+)\s*\('

            code_to_search = enhanced_code if not has_tool_decorator else ref.inline_code
            lines = code_to_search.strip().split('\n')
            for line in lines:
                line = line.strip()
                match = re.match(function_pattern, line)
                if match:
                    function_name = match.group(2)
                    if function_name in namespace:
                        tool_function = namespace[function_name]
                        logger.debug(f"🔥 Найдена функция через регулярку: {function_name}")
                        break

        if not tool_function:
            raise ValueError(f"❌ Функция не найдена в inline коде для {ref.tool_id}")

        # Проверяем, является ли функция уже tool объектом (после @tool декоратора)
        if hasattr(tool_function, '_is_platform_tool') or isinstance(tool_function, StructuredTool):
            logger.debug("🔥 Функция уже является tool объектом, возвращаем напрямую")
            return tool_function

        # Создаем StructuredTool из обычной функции
        logger.debug("🔥 Создаем StructuredTool из функции")
        tool_name = ref.tool_id.replace(".", "_")

        # Создаем простую схему без типизации
        # Простая схема только с request параметром
        SimpleSchema = create_model(
            f"{tool_name}Input",
            request=(str, Field(description="Запрос пользователя"))
        )

        return StructuredTool.from_function(
            coroutine=tool_function if asyncio.iscoroutinefunction(tool_function) else None,
            func=tool_function if not asyncio.iscoroutinefunction(tool_function) else None,
            name=tool_name,
            description=ref.description or "Кастомный инструмент",
            args_schema=SimpleSchema,
            infer_schema=False  # Отключаем автоматическое инферирование схемы
        )

    async def get_tool_namespace(self) -> Dict[str, Any]:
        """
        Возвращает namespace доступный для inline тулов.
        Используется для автокомплита и документации.
        """


        namespace = {
            'asyncio': asyncio,
            'typing': typing,
            'Annotated': typing.Annotated,
            'Optional': typing.Optional,
            'List': typing.List,
            'Dict': typing.Dict,
            'Any': typing.Any,
            '__builtins__': __builtins__,
        }

        # Добавляем импорты для типов, которые могут использоваться в inline коде
        try:
            namespace['Context'] = Context
        except ImportError:
            pass

        platform_functions = {
            'tool': tool,
            'get_context': get_context,
            'get_state': get_state,
            'send_progress': send_progress,
            'interrupt': interrupt,
            'AgentInterrupt': AgentInterrupt,
            'HumanMessage': HumanMessage,
            'AIMessage': AIMessage,
            'SystemMessage': SystemMessage,
            'ToolMessage': ToolMessage,
            # Для session_tools используем оригинальные функции из StructuredTool объектов
            'ask_user': ask_user.func if hasattr(ask_user, 'func') else ask_user,
            'session_set': session_set.func if hasattr(session_set, 'func') else session_set,
            'session_get': session_get.func if hasattr(session_get, 'func') else session_get,
            'session_has': session_has.func if hasattr(session_has, 'func') else session_has,
            'session_delete': session_delete.func if hasattr(session_delete, 'func') else session_delete,
            'session_keys': session_keys.func if hasattr(session_keys, 'func') else session_keys,
            'get_variable': get_variable.func if hasattr(get_variable, 'func') else get_variable,
        }

        namespace.update(platform_functions)
        return namespace

    async def _create_function_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из функции по CODE_REFERENCE"""
        function_path = ref.function_path or ref.tool_id

        if "." not in function_path:
            raise ValueError(f"function_path должен содержать точку (модуль.функция): {function_path}")

        module_path, name = function_path.rsplit(".", 1)
        module = self._get_cached_module(module_path)
        tool_obj = getattr(module, name)

        if inspect.isclass(tool_obj):
            return tool_obj(**ref.params)

        return tool_obj

    async def _create_agent_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из агента"""
        agent_id = ref.tool_id.removeprefix("agent:")

        agent_factory = get_agents_container().agent_factory
        agent = await agent_factory.get_agent(agent_id)

        memory_policy = ref.memory_policy
        if memory_policy is None:
            context = get_context()
            if context and context.agent_config:
                memory_policy = context.agent_config.default_memory_policy

        return agent.as_tool(description=ref.description, memory_policy=memory_policy)

    async def _create_flow_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из флоу"""
        flow_id = ref.tool_id.removeprefix("flow:")
        flow_factory = get_agents_container().flow_factory

        class FlowInput(BaseModel):
            input: str = Field(description="Входные данные для флоу")

        async def flow_func(input: str) -> str:
            flow_graph = await flow_factory.get_flow(flow_id)
            result = await flow_graph.ainvoke({"input": input})
            return str(result)

        flow_name = f"flow_{flow_id.split('.')[-1].replace('.', '_')}"
        return StructuredTool.from_function(
            coroutine=flow_func,
            name=flow_name,
            description=ref.description or f"Флоу {flow_id}",
            args_schema=FlowInput,
        )

    async def _create_mcp_tool(self, ref: ToolReference) -> Any:
        """Создает MCP инструмент"""
        parts = ref.tool_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            raise ValueError(f"Невалидный MCP tool_id: {ref.tool_id}")

        _, server_id, tool_name = parts
        company_id = ref.params.get("company_id")
        mcp_client = await get_mcp_client(server_id, company_id)

        input_schema = ref.params.get("input_schema", {})
        args_schema = self._json_schema_to_pydantic(input_schema, tool_name)
        safe_tool_name = tool_name.replace("-", "_").replace(".", "_")

        async def mcp_func(**kwargs):
            result = await mcp_client.call_tool(tool_name, kwargs)
            if result.get("isError"):
                raise ValueError(format_mcp_result(result.get("content", [])))
            return format_mcp_result(result.get("content", []))

        mcp_func.__name__ = safe_tool_name
        mcp_func.__qualname__ = safe_tool_name

        return tool(
            description=ref.description or f"MCP тул {tool_name}",
            args_schema=args_schema,
            cost=ref.cost,
            billing_name=ref.billing_name or f"mcp_{server_id}_{tool_name}",
            is_public=ref.is_public,
            state_aware=True,
            group=ref.group
        )(mcp_func)

    def _json_schema_to_pydantic(self, schema: Dict[str, Any], model_name: str):
        """Конвертирует JSON Schema в Pydantic модель для args_schema"""
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        if not properties:
            # Пустая модель если нет параметров
            return create_model(f"{model_name}Input")

        fields = {}
        for field_name, field_spec in properties.items():
            field_type = self._json_type_to_python(field_spec.get("type", "string"))
            field_description = field_spec.get("description", "")

            is_required = field_name in required
            default = ... if is_required else None

            fields[field_name] = (
                field_type,
                Field(default=default, description=field_description)
            )

        return create_model(f"{model_name}Input", **fields)

    def _json_type_to_python(self, json_type: str) -> type:
        """JSON Schema тип → Python тип"""
        mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return mapping.get(json_type, str)

    def _wrap_tool_with_billing(self, tool, tool_ref: ToolReference):
        """Оборачивает инструмент в биллинг логику"""


        # Получаем оригинальную функцию
        if hasattr(tool, 'coroutine') and tool.coroutine:
            # Асинхронная функция в StructuredTool
            original_func = tool.coroutine
        elif hasattr(tool, 'func'):
            original_func = tool.func
        else:
            original_func = tool._func

        @functools.wraps(original_func)
        async def billing_wrapper(*args, **kwargs):
            return await self._handle_tool_billing(
                original_func,
                tool_ref,
                args,
                kwargs
            )

        # Проверяем, асинхронная ли функция
        if asyncio.iscoroutinefunction(original_func):
            # Асинхронная функция - используем асинхронный биллинг
            wrapper = billing_wrapper
        else:
            # Синхронная функция - пока что без биллинга (legacy)
            logger.warning(f"⚠️ Тул {tool_ref.tool_id} синхронный - биллинг отключен. Сделайте функцию асинхронной!")
            return tool

        # Заменяем функцию в инструменте
        if hasattr(tool, 'coroutine') and tool.coroutine:
            tool.coroutine = wrapper
        elif hasattr(tool, 'func'):
            tool.func = wrapper
        else:
            tool._func = wrapper

        # Для StructuredTool нельзя менять ainvoke, биллинг работает через func

        # Добавляем метаданные биллинга
        tool._billing_ref = tool_ref

        return tool

    async def _handle_tool_billing(self, func, tool_ref: ToolReference, args, kwargs):
        """Обрабатывает биллинг для инструмента"""

        logger.info(f"🔥 ВЫЗВАН _handle_tool_billing для {tool_ref.tool_id}")
        logger.debug(f"🔥 tool_ref.billing_name = {tool_ref.billing_name}, cost = {tool_ref.cost}")

        context = get_context()

        if not context or not context.user or not context.active_company:
            raise Exception("Нет контекста для биллинга тула")

        billing_service = BillingService()
        user = context.user
        company = context.active_company
        billing_name = f"tool:{tool_ref.billing_name or tool_ref.tool_id}"

        # Проверяем можно ли использовать ресурс
        logger.debug(f"🔥 Проверяем доступ к ресурсу: {billing_name} для тарифа {company.tariff_plan}")
        can_use, reason = await billing_service.can_use_resource(user, company, billing_name)
        if not can_use:
            raise Exception(f"Доступ запрещен: {reason}")

        # Проверяем бесплатные планы
        actual_cost = 0.0 if company.tariff_plan in tool_ref.free_for_plans else tool_ref.cost

        # Выполняем асинхронную функцию
        result = await func(*args, **kwargs)

        # Записываем использование всегда для отслеживания
        await billing_service.record_usage(
            user=user,
            company=company,
            resource_name=billing_name,
            cost=actual_cost,
            usage_type=UsageType.TOOL_CALL,
            metadata={
                "tool_id": tool_ref.tool_id,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys())
            }
        )

        return result
