"""
AgentsContainer - DI контейнер для сервиса агентов.

Наследуется от BaseContainer и добавляет сервисы через @lazy декоратор.
"""

import logging
from typing import Optional

from core.container import BaseContainer, lazy

logger = logging.getLogger(__name__)


def _repository_to_prefix(repository) -> str:
    """
    Преобразует префикс репозитория в префикс пути.
    
    Использует префикс из самого репозитория.
    """
    prefix = repository.api_prefix or repository._get_prefix()
    return f"/{prefix.rstrip(':')}"


def _repository_to_tags(repository) -> list[str]:
    """
    Преобразует префикс репозитория в теги для OpenAPI.
    
    Использует префикс из самого репозитория.
    """
    prefix = repository.api_prefix or repository._get_prefix()
    tag = prefix.rstrip(':')
    return [tag]


class AgentsContainer(BaseContainer):
    """
    Контейнер для сервиса агентов.
    
    Пример:
        container = get_agents_container()
        agent = await container.agent_repository.get("my_agent")
    """
    
    # === Репозитории (service БД) ===
    
    @lazy
    def agent_repository(self):
        from apps.agents.db.repositories.agent_repository import AgentRepository
        from apps.agents.dependencies import generate_repository_dependency
        
        repository = AgentRepository(storage=self.storage)
        dependency = generate_repository_dependency("agent_repository", AgentRepository)
        
        self._register_crud_router(
            repository_name="agent_repository",
            repository=repository,
            prefix=_repository_to_prefix(repository),
            tags=_repository_to_tags(repository),
            repository_dependency=dependency
        )
        
        return repository
    
    @lazy
    def flow_repository(self):
        from apps.agents.db.repositories.flow_repository import FlowRepository
        from apps.agents.dependencies import generate_repository_dependency
        
        repository = FlowRepository(storage=self.storage)
        dependency = generate_repository_dependency("flow_repository", FlowRepository)
        
        self._register_crud_router(
            repository_name="flow_repository",
            repository=repository,
            prefix=_repository_to_prefix(repository),
            tags=_repository_to_tags(repository),
            repository_dependency=dependency
        )
        
        return repository
    
    @lazy
    def tool_repository(self):
        from apps.agents.db.repositories.tool_repository import ToolRepository
        from apps.agents.dependencies import generate_repository_dependency
        
        repository = ToolRepository(storage=self.storage)
        dependency = generate_repository_dependency("tool_repository", ToolRepository)
        
        self._register_crud_router(
            repository_name="tool_repository",
            repository=repository,
            prefix=_repository_to_prefix(repository),
            tags=_repository_to_tags(repository),
            repository_dependency=dependency
        )
        
        return repository
    
    @lazy
    def session_repository(self):
        from apps.agents.db.repositories.session_repository import SessionRepository
        from apps.agents.dependencies import generate_repository_dependency
        
        repository = SessionRepository(storage=self.storage)
        dependency = generate_repository_dependency("session_repository", SessionRepository)
        
        self._register_crud_router(
            repository_name="session_repository",
            repository=repository,
            prefix=_repository_to_prefix(repository),
            tags=_repository_to_tags(repository),
            repository_dependency=dependency
        )
        
        return repository
    
    @lazy
    def mcp_server_repository(self):
        from apps.agents.db.repositories.mcp_repository import MCPServerRepository
        from apps.agents.dependencies import generate_repository_dependency
        
        repository = MCPServerRepository(storage=self.storage)
        dependency = generate_repository_dependency("mcp_server_repository", MCPServerRepository)
        
        self._register_crud_router(
            repository_name="mcp_server_repository",
            repository=repository,
            prefix=_repository_to_prefix(repository),
            tags=_repository_to_tags(repository),
            repository_dependency=dependency
        )
        
        return repository
    
    @lazy
    def store_repository(self):
        """StoreRepository для работы с stores"""
        from apps.agents.db.repositories.store_repository import StoreRepository
        return StoreRepository(storage=self.storage)
    
    @lazy
    def agent_state_repository(self):
        """AgentStateRepository для работы с agent_states"""
        from apps.agents.db.repositories.agent_state_repository import AgentStateRepository
        return AgentStateRepository(storage=self.storage)
    
    @lazy
    def rag_repository(self):
        """RAGRepository для работы с RAG документами"""
        from core.rag import RAGRepository
        return RAGRepository()
    
    # === Фабрики ===
    
    @lazy
    def agent_factory(self):
        from apps.agents.services.agent_factory import AgentFactory
        return AgentFactory(self.agent_repository)
    
    @lazy
    def flow_factory(self):
        from apps.agents.services.flow_factory import FlowFactory
        return FlowFactory(
            flow_repository=self.flow_repository,
            session_repository=self.session_repository,
            user_repository=self.user_repository,
            company_repository=self.company_repository,
            agent_repository=self.agent_repository
        )
    
    @lazy
    def tool_factory(self):
        from apps.agents.services.tool_factory import ToolFactory
        return ToolFactory()
    
    @lazy
    def graph_builder(self):
        from apps.agents.services.graph_builder import GraphBuilder
        return GraphBuilder()
    
    @lazy
    def migrator(self):
        from apps.agents.services.migration.migrator import Migrator
        return Migrator()
    
    # === Сервисы ===
    
    @lazy
    def billing_service(self):
        from core.billing import BillingService
        return BillingService(
            company_repository=self.company_repository,
            user_repository=self.user_repository,
            usage_repository=self.usage_repository
        )
    
    @lazy
    def payment_service(self):
        from core.payments import PaymentService
        return PaymentService(company_repository=self.company_repository)
    
    @lazy
    def payment_sync_service(self):
        from core.payments import PaymentSyncService
        return PaymentSyncService(
            storage=self.storage,
            payment_service=self.payment_service
        )
    
    @lazy
    def interface_factory(self):
        from apps.agents.interfaces.factory import InterfaceFactory
        return InterfaceFactory(flow_repository=self.flow_repository)


# === Глобальный контейнер ===

_agents_container: Optional[AgentsContainer] = None


def get_agents_container() -> AgentsContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _agents_container
    if _agents_container is None:
        from core.config import get_settings
        settings = get_settings()
        _agents_container = AgentsContainer(
            service_db_url=settings.database.url,
            shared_db_url=settings.database.shared_url
        )
        logger.info("AgentsContainer инициализирован")
    return _agents_container


def reset_agents_container():
    """Сбрасывает контейнер (для тестов)"""
    global _agents_container
    _agents_container = None


# Алиас
get_container = get_agents_container
