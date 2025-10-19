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
        self._agent_repository = None
        self._flow_repository = None
        self._task_repository = None
        self._session_repository = None
        self._tool_repository = None
        self._mcp_server_repository = None
    
    def get_storage(self):
        """Получает Storage (lazy loading)"""
        if self._storage is None:
            from app.db.repositories import Storage
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
    
    def get_agent_repository(self):
        """Получает AgentRepository (lazy loading)"""
        if self._agent_repository is None:
            from app.db.repositories import AgentRepository
            self._agent_repository = AgentRepository(self.get_storage())
        return self._agent_repository
    
    def get_flow_repository(self):
        """Получает FlowRepository (lazy loading)"""
        if self._flow_repository is None:
            from app.db.repositories import FlowRepository
            self._flow_repository = FlowRepository(self.get_storage())
        return self._flow_repository
    
    def get_task_repository(self):
        """Получает TaskRepository (lazy loading)"""
        if self._task_repository is None:
            from app.db.repositories import TaskRepository
            self._task_repository = TaskRepository(self.get_storage())
        return self._task_repository
    
    def get_session_repository(self):
        """Получает SessionRepository (lazy loading)"""
        if self._session_repository is None:
            from app.db.repositories import SessionRepository
            self._session_repository = SessionRepository(self.get_storage())
        return self._session_repository
    
    def get_tool_repository(self):
        """Получает ToolRepository (lazy loading)"""
        if self._tool_repository is None:
            from app.db.repositories import ToolRepository
            self._tool_repository = ToolRepository(self.get_storage())
        return self._tool_repository
    
    def get_mcp_server_repository(self):
        """Получает MCPServerRepository (lazy loading)"""
        if self._mcp_server_repository is None:
            from app.db.repositories.mcp_repository import MCPServerRepository
            self._mcp_server_repository = MCPServerRepository(self.get_storage())
        return self._mcp_server_repository


# Глобальный контейнер
_container = Container()


def get_container() -> Container:
    """Получает глобальный контейнер зависимостей"""
    return _container
