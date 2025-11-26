"""
StateGraphAgent - агент на базе кастомного StateGraph.
Использует GraphBuilder для создания графа из graph_definition.
"""

import logging
from typing import Any, Dict, Optional

from apps.agents.agents.base import BaseAgent
from core.clients.llm import get_llm
from apps.agents.services.agent_runner import StateGraphRunner
from apps.agents.models import GraphDefinition

logger = logging.getLogger(__name__)



class StateGraphAgent(BaseAgent):
    """
    Агент на базе кастомного StateGraph.
    
    Создает граф из декларативного graph_definition через GraphBuilder.
    Переопредели метод graph_definition() для определения графа.
    """

    def graph_definition(self) -> Dict[str, Any]:
        """
        Возвращает определение графа.
        Переопредели этот метод в подклассе для определения структуры графа.
        
        Returns:
            Словарь с определением графа (nodes, edges, entry_point)
            
        Raises:
            NotImplementedError: Если метод не переопределен и нет graph_definition в config
        """
        if self.config and self.config.graph_definition:
            return self.config.graph_definition
        
        raise NotImplementedError(
            f"StateGraph агент {type(self).__name__} должен переопределить метод graph_definition() "
            f"или иметь graph_definition в конфигурации"
        )

    async def get_runner(self):
        """
        Создает StateGraphRunner для выполнения агента.
        
        Returns:
            StateGraphRunner для выполнения графа
        """
        graph_def = self.graph_definition()
        
        llm_kwargs = {}
        if self.config and self.config.llm_config:
            if self.config.llm_config.model:
                llm_kwargs["model_name"] = self.config.llm_config.model
            if self.config.llm_config.temperature is not None:
                llm_kwargs["temperature"] = self.config.llm_config.temperature
        
        llm = get_llm(**llm_kwargs) if llm_kwargs else get_llm()
        
        tools = await self.get_tools()
        if isinstance(graph_def, GraphDefinition):
            graph_definition = graph_def
        else:
            graph_definition = GraphDefinition(**graph_def)
        prompt = self.config.prompt if self.config else None
        
        runner = StateGraphRunner(
            agent_config=self.config,
            tools=tools,
            llm=llm,
            graph_definition=graph_definition,
            prompt=prompt
        )
        # Инициализируем граф сразу, чтобы ошибки обнаруживались при создании раннера
        await runner._ensure_initialized()
        return runner

