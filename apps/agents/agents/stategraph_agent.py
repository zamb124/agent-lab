"""
StateGraphAgent - агент на базе кастомного StateGraph.
Использует GraphBuilder для создания графа из graph_definition.
"""

import logging
from typing import Any, Dict

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

    def get_graph_definition(self) -> GraphDefinition:
        """
        Возвращает определение графа.
        
        Проверяет в порядке:
        1. Атрибут класса graph_definition (если это GraphDefinition)
        2. Метод graph_definition() (если переопределен в подклассе)
        3. self.config.graph_definition
        
        Returns:
            GraphDefinition объект
            
        Raises:
            NotImplementedError: Если graph_definition не найден
        """
        # Проверяем атрибут класса (может быть переопределен в подклассе как GraphDefinition)
        class_attr = getattr(type(self), 'graph_definition', None)
        if class_attr is not None and isinstance(class_attr, GraphDefinition):
            return class_attr
        
        # Проверяем метод graph_definition() в подклассе (если переопределен и это callable)
        if class_attr is not None and callable(class_attr):
            # Это метод - проверяем что это не базовый метод
            base_method = getattr(StateGraphAgent, 'get_graph_definition', None)
            if class_attr is not base_method:
                try:
                    result = class_attr(self)
                    if isinstance(result, GraphDefinition):
                        return result
                    elif isinstance(result, dict):
                        return GraphDefinition.model_validate(result)
                except NotImplementedError:
                    pass
        
        # Проверяем config
        if self.config and self.config.graph_definition:
            return self.config.graph_definition
        
        raise NotImplementedError(
            f"StateGraph агент {type(self).__name__} должен определить атрибут graph_definition "
            f"или иметь graph_definition в конфигурации"
        )

    async def get_runner(self):
        """
        Создает StateGraphRunner для выполнения агента.
        
        Returns:
            StateGraphRunner для выполнения графа
        """
        graph_definition = self.get_graph_definition()
        
        llm_kwargs = {}
        if self.config and self.config.llm_config:
            if self.config.llm_config.model:
                llm_kwargs["model_name"] = self.config.llm_config.model
            if self.config.llm_config.temperature is not None:
                llm_kwargs["temperature"] = self.config.llm_config.temperature
        
        llm = get_llm(**llm_kwargs) if llm_kwargs else get_llm()
        
        tools = await self.get_tools()
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

