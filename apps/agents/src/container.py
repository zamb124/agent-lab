"""DI контейнер."""

from typing import Optional

from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class AgentContainer(BaseContainer):
    """DI контейнер сервиса agents."""

    # Флаг выполнения через воркер. 
    # True = kiq() отправляет в воркер
    # False = kiq() выполняет локально (внутри воркера)
    use_worker: bool = True

    @lazy
    def agent_repository(self):
        from apps.agents.src.db import AgentRepository
        return AgentRepository(storage=self.storage)

    @lazy
    def node_repository(self):
        from apps.agents.src.db import NodeRepository
        return NodeRepository(storage=self.storage)

    @lazy
    def tool_repository(self):
        from apps.agents.src.db import ToolRepository
        return ToolRepository(storage=self.storage)

    @lazy
    def state_repository(self):
        from apps.agents.src.db import DatabaseStateRepository
        return DatabaseStateRepository(storage=self.storage)

    @lazy
    def state_manager(self):
        from apps.agents.src.state import StateManager
        return StateManager(state_repository=self.state_repository)

    @lazy
    def redis_client(self):
        from core.clients import RedisClient
        from apps.agents.config import get_settings
        settings = get_settings()
        redis_url = settings.database.redis_url
        client = RedisClient(redis_url)
        return client

    @lazy
    def variable_repository(self):
        from core.db.repositories import VariableRepository
        return VariableRepository(storage=self.storage)

    @lazy
    def evaluation_repository(self):
        from apps.agents.src.db import EvaluationRepository
        return EvaluationRepository(storage=self.storage)

    # push_subscription_repository наследуется из BaseContainer (core/push/)

    @lazy
    def scheduled_task_repository(self):
        from apps.agents.src.db.scheduled_task_repository import ScheduledTaskRepository
        return ScheduledTaskRepository(storage=self.storage)

    @lazy
    def mcp_server_repository(self):
        from apps.agents.src.db.mcp_repository import MCPServerRepository
        return MCPServerRepository(storage=self.storage)

    @lazy
    def resource_repository(self):
        from apps.agents.src.db import ResourceRepository
        return ResourceRepository(storage=self.storage)

    @lazy
    def resource_resolver(self):
        from apps.agents.src.resources import ResourceResolver
        return ResourceResolver(
            repository=self.resource_repository,
            container=self,
        )

    @lazy
    def variables_service(self):
        from apps.agents.src.variables import VariablesService
        return VariablesService(self.variable_repository)

    @lazy
    def evaluation_service(self):
        from apps.agents.src.evaluation import EvaluationService
        return EvaluationService(evaluation_repository=self.evaluation_repository)

    # push сервис перенесен в core/push/service.py и инициализируется в factory.py

    @lazy
    def schedule_service(self):
        from apps.agents.src.services.schedule_service import ScheduleService
        return ScheduleService(scheduled_task_repository=self.scheduled_task_repository)

    @lazy
    def a2a_client(self):
        from core.clients import A2AClient
        return A2AClient()

    @lazy
    def agent_discovery(self):
        from apps.agents.src.services import AgentDiscoveryService
        return AgentDiscoveryService(
            repository=self.agent_repository,
            a2a_client=self.a2a_client,
        )

    @lazy
    def run_inline_code(self):
        from apps.agents.src.tasks.eval_task import run_inline_code
        return run_inline_code

    @lazy
    def node_registry(self):
        from apps.agents.src.registry.nodes import create_default_node_registry
        return create_default_node_registry()

    @lazy
    def tool_registry(self):
        from apps.agents.src.tools.registry import ToolRegistry
        registry = ToolRegistry()
        registry.register_builtin_tools()
        return registry

    @lazy
    def graph_compiler(self):
        from core.compiler import GraphCompiler
        return GraphCompiler()

    @lazy
    def react_node_class(self):
        from apps.agents.src.agent.nodes import ReactNode
        return ReactNode

    @lazy
    def safe_eval_class(self):
        from apps.agents.src.eval.safe_eval import SafeEval
        return SafeEval

    @lazy
    def base_tool_class(self):
        from apps.agents.src.tools.base import BaseTool
        return BaseTool

    def get_code_runner(self, language: str = "python", resources: dict = None):
        """Возвращает runner для указанного языка."""
        from core.context import get_context
        context = get_context()
        
        if language == "python":
            from apps.agents.src.runners.python import PythonCodeRunner
            return PythonCodeRunner(context=context, resources=resources)
        elif language == "javascript":
            from apps.agents.src.runners.javascript import JavaScriptCodeRunner
            return JavaScriptCodeRunner()
        else:
            raise ValueError(f"Unsupported language: {language}")

    @lazy
    def resource_loader(self):
        from apps.agents.src.services.resource_loader import ResourceLoader
        return ResourceLoader(
            node_registry=self.node_registry,
            tool_registry=self.tool_registry,
            agent_repository=self.agent_repository,
            node_repository=self.node_repository,
            tool_repository=self.tool_repository,
        )

    @lazy
    def llm_model_repository(self):
        from apps.agents.src.db import LLMModelRepository
        return LLMModelRepository(storage=self.storage)

    @lazy
    def llm_models_service(self):
        from apps.agents.src.services import LLMModelsService
        return LLMModelsService(repository=self.llm_model_repository)

    @lazy
    def agent_factory(self):
        from apps.agents.src.services import AgentFactory
        return AgentFactory(
            agent_repository=self.agent_repository,
            variables_service=self.variables_service,
            graph_compiler=self.graph_compiler,
        )
    
    @lazy
    def trigger_registry(self):
        from apps.agents.config import get_settings
        from apps.agents.src.triggers import TriggerRegistry
        from apps.agents.src.triggers.handlers.telegram import TelegramTriggerHandler
        from apps.agents.src.models import TriggerType
        
        settings = get_settings()
        base_url = settings.server.get_service_url()
        
        registry = TriggerRegistry(base_url=base_url)
        
        # Регистрируем handlers
        registry.register_handler(TriggerType.TELEGRAM, TelegramTriggerHandler)
        
        return registry
    
    @lazy
    def channel_registry(self):
        from apps.agents.src.channels import create_default_channel_registry
        return create_default_channel_registry()

    @lazy
    def embed_mapping_repository(self):
        """Репозиторий для глобального маппинга embed_id -> company_id"""
        from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
        return EmbedMappingRepository(storage=self.shared_storage)
    
    @lazy
    def embed_config_repository(self):
        """Репозиторий для конфигураций встраиваемых виджетов"""
        from core.db.repositories.embed_config_repository import EmbedConfigRepository
        return EmbedConfigRepository(storage=self.shared_storage)

    def get_channel(self, name: str, agent_id: str):
        from apps.agents.src.channels.factory import get_channel
        return get_channel(name, agent_id)


_container: Optional[AgentContainer] = None


def get_container() -> AgentContainer:
    """Получает контейнер (создает при первом вызове)"""
    import os
    global _container
    if _container is None:
        from apps.agents.config import get_settings
        settings = get_settings()
        _container = AgentContainer(
            db_url=settings.database.url,
            shared_db_url=settings.database.shared_url
        )
        # В тестах по умолчанию без воркера
        if os.environ.get("TESTING") == "true":
            _container.use_worker = False
        logger.info("AgentContainer создан")
    return _container


def set_container(container: AgentContainer) -> None:
    """Устанавливает контейнер (для тестов)"""
    global _container
    _container = container


def reset_container() -> None:
    """Сбрасывает контейнер"""
    global _container
    _container = None
