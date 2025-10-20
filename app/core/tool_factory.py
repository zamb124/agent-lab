"""
Фабрика для создания инструментов на основе конфигурации.
"""

import logging
import importlib
import inspect
import functools
import asyncio
from typing import List, Any, Dict
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import typing
from app.models import ToolReference, CodeMode
from app.core.flow_factory import FlowFactory
from app.core.container import get_container
from app.core.context import get_context
from app.core.variables import get_state
from app.core.progress_sender import send_progress
from app.tools.session.session_tools import (
    session_set, session_get, session_has, session_delete, session_keys, get_variable
)
from app.tools.misc.standard import ask_user
from app.core.tool_decorator import tool
from langgraph.types import interrupt
from app.services.billing_service import BillingService
from app.models.billing_models import UsageType

logger = logging.getLogger(__name__)


class ToolFactory:
    """Фабрика для создания инструментов с кэшированием"""

    def __init__(self):
        self._tool_cache = {}
        self._module_cache = {}

    def _get_cached_module(self, module_path: str, reload: bool = False):
        """
        Получает модуль с кэшированием.
        
        Args:
            module_path: Путь к модулю
            reload: Принудительно перезагрузить модуль
            
        Returns:
            Загруженный модуль
        """
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
        """
        Создает экземпляры инструментов по списку ToolReference из БД.

        Args:
            tool_refs: Список ссылок на инструменты

        Returns:
            Список созданных инструментов
        """
        created_tools = []

        for ref in tool_refs:
            try:
                tool_instance = await self._create_single_tool(ref)
                if tool_instance is not None:
                    created_tools.append(tool_instance)
            except Exception as e:
                logger.error(f"Не удалось создать инструмент '{ref.tool_id}': {e}")
                # Не падаем, просто пропускаем сломанный инструмент
                continue

        logger.info(
            f"Создано {len(created_tools)} инструментов из {len(tool_refs)} запрошенных"
        )
        return created_tools

    async def _create_single_tool(self, ref: ToolReference) -> Any:
        """Создает один инструмент по ссылке с поддержкой биллинга"""
        tool_id = ref.tool_id

        # Создаем базовый инструмент
        if ref.code_mode == CodeMode.MCP_TOOL:
            tool = await self._create_mcp_tool(ref)
        elif tool_id.startswith("agent:") or "agents" in tool_id:
            tool = await self._create_agent_tool(ref)
        elif tool_id.startswith("flow:") or "flows" in tool_id:
            tool = await self._create_flow_tool(ref)
        elif ref.code_mode == CodeMode.INLINE_CODE:
            tool = await self._create_inline_code_tool(ref)
        elif ref.code_mode == CodeMode.CODE_REFERENCE:
            tool = await self._create_function_tool(ref)
        else:
            raise ValueError(f"Неизвестный тип тула: code_mode={ref.code_mode}, tool_id={ref.tool_id}")

        if tool is None:
            logger.warning(f"⚠️ Tool {tool_id} returned None - не создан")
            return None

        # Оборачиваем в биллинг если есть стоимость или лимиты
        if ref.cost > 0 or ref.tariff_limits or ref.free_for_plans:
            tool = self._wrap_tool_with_billing(tool, ref)

        return tool

    async def _create_inline_code_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из inline кода"""
        if not ref.inline_code:
            raise ValueError(f"INLINE_CODE инструмент {ref.tool_id} не содержит inline_code")
        
        try:
            logger.debug(f"🔥 Создаем INLINE_CODE инструмент: {ref.tool_id}")
            logger.debug(f"🔥 Inline код: {ref.inline_code[:100]}...")
            
            # Создаем namespace для выполнения кода с необходимыми импортами
            # Используем тот же namespace, что и для документации
            namespace = self.get_tool_namespace()
            
            # Выполняем inline код
            exec(ref.inline_code, namespace, namespace)
            
            # Ищем функцию main или первую async функцию
            tool_function = namespace.get('main')
            if not tool_function:
                # Ищем первую async функцию или tool объект
                for name, obj in namespace.items():
                    if name.startswith('_'):
                        continue
                    if asyncio.iscoroutinefunction(obj) or callable(obj):
                        tool_function = obj
                        logger.debug(f"🔥 Найдена функция: {name}")
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
            return StructuredTool.from_function(
                coroutine=tool_function if asyncio.iscoroutinefunction(tool_function) else None,
                func=tool_function if not asyncio.iscoroutinefunction(tool_function) else None,
                name=tool_name,
                description=ref.description or "Кастомный инструмент"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания INLINE_CODE инструмента {ref.tool_id}: {e}")
            raise

    def get_tool_namespace(self) -> Dict[str, Any]:
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

        # Добавляем платформенные функции
        platform_functions = {
            'tool': tool,
            'get_context': get_context,
            'get_state': get_state,
            'send_progress': send_progress,
            'interrupt': interrupt,
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
        """Создает инструмент из обычной функции или класса"""
        # Используем function_path если есть, иначе tool_id
        function_path = ref.function_path or ref.tool_id

        try:
            # Специальная обработка для MCP tools
            if function_path.startswith("mcp:"):
                # MCP tools обрабатываются отдельно, возвращаем None для пропуска
                return None

            # Для INLINE_CODE точка не обязательна (может быть просто именем функции)
            if ref.code_mode == CodeMode.INLINE_CODE:
                # Inline code - ищем функцию в глобальном пространстве или создаем динамически
                if "." in function_path:
                    module_path, name = function_path.rsplit(".", 1)
                    module = self._get_cached_module(module_path)
                    tool_obj = getattr(module, name)
                else:
                    # Ищем в глобальном пространстве имен
                    tool_obj = globals().get(function_path)
                    if tool_obj is None:
                        # Для inline code функция может создаваться динамически
                        # Возвращаем None, чтобы инструмент создался другим способом
                        return None
            else:
                # Для CODE_REFERENCE точка обязательна
                if "." not in function_path:
                    raise ValueError(f"function_path должен содержать точку (модуль.функция): {function_path}")

                module_path, name = function_path.rsplit(".", 1)
                module = self._get_cached_module(module_path)
                tool_obj = getattr(module, name)

            # Если это класс, создаем экземпляр
            if inspect.isclass(tool_obj):
                # Передаем параметры в конструктор, если они есть
                return tool_obj(**ref.params)
            else:
                # Это функция, возвращаем как есть
                return tool_obj

        except Exception as e:
            logger.error(f"Ошибка создания функции-инструмента {function_path}: {e}")
            raise

    async def _create_agent_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из агента"""

        try:
            # Убираем префикс agent: если он есть
            agent_class_path = ref.tool_id
            if agent_class_path.startswith("agent:"):
                agent_class_path = agent_class_path[6:]  # Убираем 'agent:'

            # Получаем агента через контейнер
            container = get_container()
            agent_factory = container.get_agent_factory()
            agent = await agent_factory.get_agent(agent_class_path)

            # Превращаем агента в инструмент
            return agent.as_tool()

        except Exception as e:
            logger.error(f"Ошибка создания агента-инструмента {ref.tool_id}: {e}")
            raise

    async def _create_flow_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из флоу"""

        class FlowInput(BaseModel):
            input: str = Field(description="Входные данные для флоу")

        try:
            flow_factory = FlowFactory()

            async def flow_func(input: str) -> str:
                """Функция-обертка для вызова флоу как инструмента"""
                try:
                    flow_graph = await flow_factory.get_flow(ref.tool_id)
                    result = await flow_graph.ainvoke({"input": input})
                    return str(result)
                except Exception as e:
                    return f"Ошибка выполнения флоу: {str(e)}"

            flow_name = f"flow_{ref.tool_id.split('.')[-1].replace('.', '_')}"
            return StructuredTool.from_function(
                func=flow_func,
                name=flow_name,
                description=f"Флоу {ref.tool_id}",
                args_schema=FlowInput,
            )

        except Exception as e:
            logger.error(f"Ошибка создания флоу-инструмента {ref.tool_id}: {e}")
            raise

    async def _create_mcp_tool(self, ref: ToolReference) -> Any:
        """
        Создает MCP инструмент через @tool декоратор.

        Динамически создает функцию и оборачивает её в @tool для
        единообразия с остальными тулами платформы.
        """
        logger.info(f"🎯 Создание MCP tool: {ref.tool_id}")
        from app.core.mcp_client import get_mcp_client, format_mcp_result
        from app.core.tool_decorator import tool
        from pydantic import create_model, Field as PydanticField

        # Проверяем CodeMode для безопасности
        if ref.code_mode != CodeMode.MCP_TOOL:
            logger.warning(f"⚠️ Ожидался CodeMode.MCP_TOOL для {ref.tool_id}, получен {ref.code_mode}")
            raise ValueError(f"Ожидался CodeMode.MCP_TOOL для {ref.tool_id}, получен {ref.code_mode}")

        # Парсим tool_id: "mcp:server_id:tool_name"
        parts = ref.tool_id.split(":", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            logger.error(f"❌ Невалидный MCP tool_id: {ref.tool_id}")
            raise ValueError(f"Невалидный MCP tool_id: {ref.tool_id}")

        _, server_id, tool_name = parts
        logger.info(f"📦 Разобран MCP tool: server={server_id}, tool={tool_name}")

        # Получаем company_id из params
        company_id = ref.params.get("company_id")
        logger.info(f"🏢 Company ID: {company_id}")

        # Получаем HTTP клиент для этого MCP сервера
        try:
            mcp_client = await get_mcp_client(server_id, company_id)
            logger.info(f"🌐 MCP клиент получен для сервера {server_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось получить MCP клиент: {e}")
            return None
        
        # Получаем схему из params
        input_schema = ref.params.get("input_schema", {})
        
        # Создаем Pydantic модель из JSON Schema
        args_schema = self._json_schema_to_pydantic(input_schema, tool_name)
        
        # Создаем функцию с валидным Python именем
        safe_tool_name = tool_name.replace("-", "_").replace(".", "_")
        
        # Создаем функцию с нужным именем ДО применения декоратора
        async def dynamic_mcp_func(**kwargs):
            """Динамически созданная функция для вызова MCP тула"""
            try:
                # Вызываем MCP тул через HTTP/SSE
                result = await mcp_client.call_tool(tool_name, kwargs)
                
                # Обрабатываем ошибки
                if result.get("isError"):
                    error_msg = format_mcp_result(result.get("content", []))
                    logger.error(f"MCP тул {tool_name} вернул ошибку: {error_msg}")
                    return f"❌ Ошибка: {error_msg}"
                
                # Форматируем успешный результат
                formatted = format_mcp_result(result.get("content", []))
                logger.info(f"✅ MCP тул {tool_name} выполнен")
                
                return formatted
                
            except Exception as e:
                logger.error(f"Ошибка вызова MCP тула {tool_name}: {e}", exc_info=True)
                raise ValueError(f"Ошибка MCP тула: {str(e)}") from e
        
        # Устанавливаем имя ДО декоратора
        dynamic_mcp_func.__name__ = safe_tool_name
        dynamic_mcp_func.__qualname__ = safe_tool_name
        
        # Применяем @tool декоратор
        try:
            mcp_tool = tool(
                description=ref.description or f"MCP тул {tool_name}",
                args_schema=args_schema,
                cost=ref.cost,
                billing_name=ref.billing_name or f"mcp_{server_id}_{tool_name}",
                is_public=ref.is_public,
                state_aware=True,
                group=ref.group
            )(dynamic_mcp_func)

            logger.info(f"✅ MCP tool {ref.tool_id} успешно создан")
            return mcp_tool

        except Exception as e:
            logger.error(f"❌ Ошибка создания MCP tool {ref.tool_id}: {e}")
            return None
    
    def _json_schema_to_pydantic(self, schema: Dict[str, Any], model_name: str):
        """Конвертирует JSON Schema в Pydantic модель для args_schema"""
        from pydantic import create_model, Field as PydanticField
        
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
                PydanticField(default=default, description=field_description)
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
