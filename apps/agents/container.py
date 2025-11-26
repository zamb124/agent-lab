"""
AgentsContainer - DI контейнер для сервиса агентов.

Наследуется от BaseContainer и добавляет:
- Репозитории: agent_repository, flow_repository, tool_repository, task_repository, session_repository
- Фабрики: agent_factory, flow_factory, tool_factory
- Сервисы: graph_builder, migrator

Поддерживает:
- service БД (agents_db) - для agents, flows, tools
- shared БД (shared_db) - для users, companies, files, sessions
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from core.container import BaseContainer
from core.db.storage import Storage
from core.context import get_context

if TYPE_CHECKING:
    from apps.agents.db.repositories.agent_repository import AgentRepository
    from apps.agents.db.repositories.flow_repository import FlowRepository
    from apps.agents.db.repositories.tool_repository import ToolRepository
    from apps.agents.db.repositories.task_repository import TaskRepository
    from apps.agents.db.repositories.session_repository import SessionRepository
    from apps.agents.db.repositories.mcp_repository import MCPServerRepository
    from apps.agents.services.agent_factory import AgentFactory
    from apps.agents.services.flow_factory import FlowFactory
    from apps.agents.services.tool_factory import ToolFactory
    from apps.agents.services.graph_builder import GraphBuilder
    from apps.agents.services.migration.migrator import Migrator
    from core.billing import BillingService
    from core.payments import PaymentService, PaymentSyncService
    from apps.agents.interfaces.factory import InterfaceFactory
    from core.variables import VariablesService

logger = logging.getLogger(__name__)


class AgentsContainer(BaseContainer):
    """
    Контейнер для сервиса агентов.
    
    Расширяет BaseContainer добавляя специфичные для агентов сервисы.
    """

    def __init__(self, service_db_url: Optional[str] = None, shared_db_url: Optional[str] = None):
        """
        Args:
            service_db_url: URL БД для сервиса (agents, flows, tools)
            shared_db_url: URL shared БД (users, companies, files, sessions)
        """
        super().__init__(db_url=service_db_url, shared_db_url=shared_db_url)
        
        self._variables_service: Optional["VariablesService"] = None
        
        self._agent_repository: Optional["AgentRepository"] = None
        self._flow_repository: Optional["FlowRepository"] = None
        self._tool_repository: Optional["ToolRepository"] = None
        self._task_repository: Optional["TaskRepository"] = None
        self._session_repository: Optional["SessionRepository"] = None
        
        self._agent_factory: Optional["AgentFactory"] = None
        self._flow_factory: Optional["FlowFactory"] = None
        self._tool_factory: Optional["ToolFactory"] = None
        self._graph_builder: Optional["GraphBuilder"] = None
        self._migrator: Optional["Migrator"] = None
        
        self._mcp_server_repository: Optional["MCPServerRepository"] = None
        self._billing_service: Optional["BillingService"] = None
        self._payment_service: Optional["PaymentService"] = None
        self._payment_sync_service: Optional["PaymentSyncService"] = None
        self._interface_factory: Optional["InterfaceFactory"] = None

    def __getattr__(self, name: str):
        """Ленивая инициализация сервисов"""
        
        if name == 'agent_repository':
            if self._agent_repository is None:
                from apps.agents.db.repositories.agent_repository import AgentRepository
                self._agent_repository = AgentRepository(storage=self.storage)
                logger.debug("AgentRepository инициализирован")
            return self._agent_repository
        
        if name == 'flow_repository':
            if self._flow_repository is None:
                from apps.agents.db.repositories.flow_repository import FlowRepository
                self._flow_repository = FlowRepository(storage=self.storage)
                logger.debug("FlowRepository инициализирован")
            return self._flow_repository
        
        if name == 'tool_repository':
            if self._tool_repository is None:
                from apps.agents.db.repositories.tool_repository import ToolRepository
                self._tool_repository = ToolRepository(storage=self.storage)
                logger.debug("ToolRepository инициализирован")
            return self._tool_repository
        
        if name == 'task_repository':
            if self._task_repository is None:
                from apps.agents.db.repositories.task_repository import TaskRepository
                self._task_repository = TaskRepository(storage=self.storage)
                logger.debug("TaskRepository инициализирован")
            return self._task_repository
        
        if name == 'session_repository':
            if self._session_repository is None:
                from apps.agents.db.repositories.session_repository import SessionRepository
                self._session_repository = SessionRepository(storage=self.storage)
                logger.debug("SessionRepository инициализирован")
            return self._session_repository
        
        if name == 'agent_factory':
            if self._agent_factory is None:
                from apps.agents.services.agent_factory import AgentFactory
                self._agent_factory = AgentFactory(self.agent_repository)
                logger.debug("AgentFactory инициализирован")
            return self._agent_factory
        
        if name == 'flow_factory':
            if self._flow_factory is None:
                from apps.agents.services.flow_factory import FlowFactory
                self._flow_factory = FlowFactory(
                    flow_repository=self.flow_repository,
                    session_repository=self.session_repository,
                    user_repository=self.user_repository,
                    company_repository=self.company_repository,
                    agent_repository=self.agent_repository
                )
                logger.debug("FlowFactory инициализирован")
            return self._flow_factory
        
        if name == 'tool_factory':
            if self._tool_factory is None:
                from apps.agents.services.tool_factory import ToolFactory
                self._tool_factory = ToolFactory()
                logger.debug("ToolFactory инициализирован")
            return self._tool_factory
        
        if name == 'graph_builder':
            if self._graph_builder is None:
                from apps.agents.services.graph_builder import GraphBuilder
                self._graph_builder = GraphBuilder()
                logger.debug("GraphBuilder инициализирован")
            return self._graph_builder
        
        if name == 'migrator':
            if self._migrator is None:
                from apps.agents.services.migration.migrator import Migrator
                self._migrator = Migrator()
                logger.debug("Migrator инициализирован")
            return self._migrator
        
        if name == 'variables_service':
            if self._variables_service is None:
                from core.variables import VariablesService
                self._variables_service = VariablesService(
                    variable_repository=self.variable_repository
                )
                logger.debug("VariablesService инициализирован")
            return self._variables_service
        
        if name == 'mcp_server_repository':
            if self._mcp_server_repository is None:
                from apps.agents.db.repositories.mcp_repository import MCPServerRepository
                self._mcp_server_repository = MCPServerRepository(storage=self.storage)
                logger.debug("MCPServerRepository инициализирован")
            return self._mcp_server_repository
        
        if name == 'billing_service':
            if self._billing_service is None:
                from core.billing import BillingService
                self._billing_service = BillingService(
                    company_repository=self.company_repository,
                    user_repository=self.user_repository,
                    usage_repository=self.usage_repository
                )
                logger.debug("BillingService инициализирован")
            return self._billing_service
        
        if name == 'payment_service':
            if self._payment_service is None:
                from core.payments import PaymentService
                self._payment_service = PaymentService(
                    company_repository=self.company_repository
                )
                logger.debug("PaymentService инициализирован")
            return self._payment_service
        
        if name == 'payment_sync_service':
            if self._payment_sync_service is None:
                from core.payments import PaymentSyncService
                self._payment_sync_service = PaymentSyncService(
                    storage=self.storage,
                    payment_service=self.payment_service
                )
                logger.debug("PaymentSyncService инициализирован")
            return self._payment_sync_service
        
        if name == 'interface_factory':
            if self._interface_factory is None:
                from apps.agents.interfaces.factory import InterfaceFactory
                self._interface_factory = InterfaceFactory(
                    flow_repository=self.flow_repository
                )
                logger.debug("InterfaceFactory инициализирован")
            return self._interface_factory
        
        return super().__getattr__(name)


_agents_container: Optional[AgentsContainer] = None


def get_agents_container() -> AgentsContainer:
    """Получает контейнер сервиса агентов"""
    global _agents_container
    if _agents_container is None:
        raise RuntimeError("AgentsContainer не инициализирован! Вызовите set_agents_container() при старте приложения.")
    return _agents_container


def set_agents_container(container: AgentsContainer) -> None:
    """Устанавливает контейнер сервиса агентов"""
    global _agents_container
    _agents_container = container
    logger.info("AgentsContainer установлен")


def initialize_agents_container(
    service_db_url: Optional[str] = None,
    shared_db_url: Optional[str] = None
) -> AgentsContainer:
    """
    Инициализирует контейнер сервиса агентов.
    
    Args:
        service_db_url: URL service БД (agents, flows, tools, tasks, sessions)
        shared_db_url: URL shared БД (users, companies)
        
    Returns:
        Инициализированный AgentsContainer
    """
    global _agents_container
    if _agents_container is None:
        _agents_container = AgentsContainer(
            service_db_url=service_db_url,
            shared_db_url=shared_db_url
        )
        logger.info("AgentsContainer инициализирован")
    return _agents_container


get_container = get_agents_container
initialize_system_container = initialize_agents_container
