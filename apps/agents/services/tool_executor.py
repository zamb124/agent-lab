"""
Исполнитель инструментов для агентов.
Централизует логику выполнения инструментов.
"""

import asyncio
import logging
import uuid
from typing import List, Any, Dict, Optional
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from apps.agents.container import get_agents_container
from apps.agents.services.state import State
from apps.agents.services.tracing.decorators import trace_span
from apps.agents.models.trace_models import SpanType
from apps.agents.agents.base import AgentInterrupt

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Исполнитель инструментов для агентов"""

    def __init__(self):
        self.tool_factory = get_agents_container().tool_factory

    @trace_span(
        name="tool_executor.execute",
        span_type=SpanType.OTHER,
        metadata={"component": "tool_executor", "operation": "execute"}
    )
    async def execute(
        self, 
        tool_calls: List[Dict[str, Any]], 
        tools: List[Any],
        state: Optional[State] = None
    ) -> List[ToolMessage]:
        """
        Выполняет инструменты по запросу от LLM.

        Args:
            tool_calls: Список вызовов инструментов от LLM
            tools: Список доступных инструментов
            state: Текущее состояние агента (опционально, для state_aware инструментов)

        Returns:
            Список ToolMessage с результатами выполнения
        """
        if not tool_calls:
            logger.debug("Нет tool_calls для выполнения")
            return []

        tool_messages = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("args") or tool_call.get("arguments") or tool_call.get("function", {}).get("arguments", {})
            tool_call_id = tool_call.get("id") or str(uuid.uuid4())
            
            if not tool_name:
                logger.warning(f"Пропускаем tool_call без имени: {tool_call}")
                continue

            tool = self._find_tool(tool_name, tools)
            if not tool:
                error_msg = f"Инструмент '{tool_name}' не найден"
                logger.error(error_msg)
                tool_messages.append(
                    ToolMessage(
                        content=f"Ошибка: {error_msg}",
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                )
                continue

            try:
                result = await self._execute_tool(tool, tool_args, state, tool_call_id)
                
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                )
                logger.info(f"Инструмент '{tool_name}' выполнен успешно")
            except AgentInterrupt as interrupt:
                if hasattr(tool, '_is_agent_tool') and tool._is_agent_tool:
                    raise interrupt
                tool_messages.append(
                    ToolMessage(
                        content=f"Ошибка: {str(interrupt)}",
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                )
                raise interrupt
            
        return tool_messages

    def _find_tool(self, tool_name: str, tools: List[Any]) -> Optional[Any]:
        """
        Находит инструмент по имени в списке доступных инструментов.

        Args:
            tool_name: Имя инструмента
            tools: Список доступных инструментов

        Returns:
            Найденный инструмент или None
        """
        for tool in tools:
            if hasattr(tool, "name") and tool.name == tool_name:
                return tool
            if isinstance(tool, StructuredTool) and tool.name == tool_name:
                return tool
        
        logger.warning(f"Инструмент '{tool_name}' не найден среди {len(tools)} доступных")
        return None

    async def _execute_tool(
        self, 
        tool: Any, 
        tool_args: Dict[str, Any], 
        state: Optional[State],
        tool_call_id: str
    ) -> Any:
        """
        Выполняет один инструмент.

        Args:
            tool: Инструмент для выполнения
            tool_args: Аргументы для инструмента
            state: Текущее состояние (для state_aware инструментов)
            tool_call_id: ID вызова инструмента

        Returns:
            Результат выполнения инструмента
        """
        if not isinstance(tool_args, dict):
            tool_args = {}

        if state is not None:
            from core.variables import set_state_in_context
            
            if hasattr(tool, '_is_platform_tool') and tool._is_platform_tool:
                set_state_in_context(state)
                logger.debug(f"State установлен в контекст для тула '{tool.name}' (state_aware)")
            
            if hasattr(tool, 'args_schema') and tool.args_schema:
                schema_fields = tool.args_schema.model_fields if hasattr(tool.args_schema, 'model_fields') else {}
                
                if 'tool_call_id' in schema_fields and 'tool_call_id' not in tool_args:
                    tool_args['tool_call_id'] = tool_call_id
                    logger.debug(f"Добавляем tool_call_id в аргументы тула '{tool.name}'")

        if hasattr(tool, "ainvoke"):
            result = await tool.ainvoke(tool_args)
        elif hasattr(tool, "invoke"):
            result = tool.invoke(tool_args)
        else:
            if callable(tool):
                if asyncio.iscoroutinefunction(tool):
                    result = await tool(**tool_args)
                else:
                    result = tool(**tool_args)
            else:
                raise ValueError(f"Инструмент '{tool.name}' не может быть выполнен")

        return result

