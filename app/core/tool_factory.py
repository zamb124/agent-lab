"""
Фабрика для создания инструментов на основе конфигурации.
"""

import logging
import importlib
import inspect
import functools
import asyncio
from typing import List, Any
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.models import ToolReference, CodeMode
from app.core.flow_factory import FlowFactory
from app.core.container import get_container
from app.core.context import get_context
from app.services.billing_service import BillingService
from app.models.billing_models import UsageType, TARIFF_LIMITS

logger = logging.getLogger(__name__)


class ToolFactory:
    """Фабрика для создания инструментов"""

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
        if tool_id.startswith("mcp:"):
            tool = await self._create_mcp_tool(ref)
        elif "agents" in tool_id:
            tool = await self._create_agent_tool(ref)
        elif "flows" in tool_id:
            tool = await self._create_flow_tool(ref)
        elif ref.code_mode == CodeMode.INLINE_CODE:
            tool = await self._create_inline_code_tool(ref)
        else:
            tool = await self._create_function_tool(ref)
        
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
            
            # Создаем namespace для выполнения кода
            namespace = {'asyncio': asyncio}
            
            # Выполняем inline код
            exec(ref.inline_code, namespace)
            
            # Ищем функцию main или первую async функцию
            tool_function = namespace.get('main')
            if not tool_function:
                # Ищем первую async функцию
                for name, obj in namespace.items():
                    if name.startswith('_'):
                        continue
                    if asyncio.iscoroutinefunction(obj) or callable(obj):
                        tool_function = obj
                        logger.debug(f"🔥 Найдена функция: {name}")
                        break
            
            if not tool_function:
                # Если функция не найдена, создаем простую заглушку
                logger.warning(f"⚠️ Функция не найдена в inline коде, создаем заглушку")
                async def stub_function(*args, **kwargs):
                    return "Результат"
                tool_function = stub_function
            
            # Создаем StructuredTool из функции
            logger.debug(f"🔥 Создаем StructuredTool из функции")
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

    async def _create_function_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из обычной функции или класса"""
        # Используем function_path если есть, иначе tool_id
        function_path = ref.function_path or ref.tool_id

        try:
            # Разделяем путь на модуль и имя объекта
            module_path, name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
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
        """Создает MCP инструмент"""
        # Заглушка для MCP инструментов
        # В будущем здесь будет интеграция с Model Context Protocol
        logger.warning(f"MCP инструменты пока не поддерживаются: {ref.tool_id}")
        return None
    
    def _wrap_tool_with_billing(self, tool, tool_ref: ToolReference):
        """Оборачивает инструмент в биллинг логику"""
        
        billing_name = tool_ref.billing_name or tool_ref.tool_id
        
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
