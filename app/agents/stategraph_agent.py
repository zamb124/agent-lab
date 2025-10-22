"""
StateGraphAgent - агент на базе кастомного StateGraph.
Использует GraphBuilder для создания графа из graph_definition.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.runnables import Runnable

from app.agents.base import BaseAgent
from app.core.container import get_container

logger = logging.getLogger(__name__)


class StateGraphAgent(BaseAgent):
    """
    Агент на базе кастомного StateGraph.
    
    Создает граф из декларативного graph_definition через GraphBuilder.
    Требует наличия graph_definition в конфигурации.
    """

    async def compile_graph(self) -> Runnable:
        """
        Компилирует StateGraph из graph_definition.
        
        Returns:
            Скомпилированный граф LangGraph
            
        Raises:
            ValueError: Если не указан graph_definition в конфигурации
        """
        logger.info(f"Компиляция StateGraph графа для агента: {self.config.agent_id}")
        
        if not self.config.graph_definition:
            raise ValueError(
                f"StateGraph агент {self.config.agent_id} требует graph_definition"
            )

        container = get_container()
        builder = container.graph_builder
        graph = await builder.build_from_definition(
            self.config.graph_definition, 
            self.config.llm_config
        )

        logger.info(f"StateGraph граф создан для агента {self.config.agent_id}")
        return graph

