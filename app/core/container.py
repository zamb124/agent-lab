"""
Dependency Injection Container для управления зависимостями.
Решает проблему циклических импортов через lazy loading.
"""

import logging

logger = logging.getLogger(__name__)


class Container:
    """Контейнер зависимостей для lazy loading"""
    
    def __init__(self):
        self._storage = None
        self._agent_factory = None
        self._tool_factory = None
        self._flow_factory = None
        self._graph_builder = None
    
    def get_storage(self):
        """Получает Storage (lazy loading)"""
        if self._storage is None:
            from app.core.storage import Storage
            self._storage = Storage()
        return self._storage
    
    def get_agent_factory(self):
        """Получает AgentFactory (lazy loading)"""
        if self._agent_factory is None:
            from app.core.agent_factory import AgentFactory
            self._agent_factory = AgentFactory()
        return self._agent_factory
    
    def get_tool_factory(self):
        """Получает ToolFactory (lazy loading)"""
        if self._tool_factory is None:
            from app.core.tool_factory import ToolFactory
            self._tool_factory = ToolFactory()
        return self._tool_factory
    
    def get_flow_factory(self):
        """Получает FlowFactory (lazy loading)"""
        if self._flow_factory is None:
            from app.core.flow_factory import FlowFactory
            self._flow_factory = FlowFactory()
        return self._flow_factory
    
    def get_graph_builder(self):
        """Получает GraphBuilder (lazy loading)"""
        if self._graph_builder is None:
            from app.core.graph_builder import GraphBuilder
            self._graph_builder = GraphBuilder()
        return self._graph_builder


# Глобальный контейнер
_container = Container()


def get_container() -> Container:
    """Получает глобальный контейнер зависимостей"""
    return _container
