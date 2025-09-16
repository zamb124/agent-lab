"""
Фабрика для создания инструментов на основе конфигурации.
"""
import logging
import importlib
import inspect
from typing import List, Any
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.models import ToolReference
# Избегаем циклических импортов - импортируем внутри функций при необходимости

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
        
        logger.info(f"Создано {len(created_tools)} инструментов из {len(tool_refs)} запрошенных")
        return created_tools
    
    async def _create_single_tool(self, ref: ToolReference) -> Any:
        """Создает один инструмент по ссылке"""
        tool_id = ref.tool_id
        
        if tool_id.startswith('mcp:'):
            return await self._create_mcp_tool(ref)
        elif 'agents' in tool_id:
            return await self._create_agent_tool(ref)
        elif 'flows' in tool_id:
            return await self._create_flow_tool(ref)
        else:
            return await self._create_function_tool(ref)
    
    async def _create_function_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из обычной функции или класса"""
        tool_id = ref.tool_id
        
        try:
            # Разделяем путь на модуль и имя объекта
            module_path, name = tool_id.rsplit('.', 1)
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
            logger.error(f"Ошибка создания функции-инструмента {tool_id}: {e}")
            raise
    
    async def _create_agent_tool(self, ref: ToolReference) -> Any:
        """Создает инструмент из агента"""
        
        try:
            # Убираем префикс agent: если он есть
            agent_class_path = ref.tool_id
            if agent_class_path.startswith('agent:'):
                agent_class_path = agent_class_path[6:]  # Убираем 'agent:'
            
            # Получаем агента через фабрику
            from app.core.agent_factory import AgentFactory
            agent_factory = AgentFactory()
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
            from app.core.flow_factory import FlowFactory
            flow_factory = FlowFactory()
            
            async def flow_func(input: str) -> str:
                """Функция-обертка для вызова флоу как инструмента"""
                try:
                    flow_graph = await flow_factory.get_flow(ref.tool_id)
                    result = await flow_graph.ainvoke({"input": input})
                    return str(result)
                except Exception as e:
                    return f"Ошибка выполнения флоу: {str(e)}"
            
            return StructuredTool.from_function(
                func=flow_func,
                name=f"flow_{ref.tool_id.split('.')[-1]}",
                description=f"Флоу {ref.tool_id}",
                args_schema=FlowInput
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
