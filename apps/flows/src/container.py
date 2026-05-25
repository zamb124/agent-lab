"""DI контейнер."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from apps.flows.config import get_settings
from apps.flows.src.channels.factory import get_channel as build_channel
from apps.flows.src.channels.registry import ChannelRegistry, create_default_channel_registry
from apps.flows.src.container_contracts import FlowRuntimeContainer, as_flow_runtime_container
from apps.flows.src.container_state import (
    get_current_container,
    reset_current_container,
    set_current_container,
)
from apps.flows.src.db import (
    EvaluationRepository,
    FlowRepository,
    LLMModelRepository,
    NodeRepository,
    ResourceRepository,
    ToolRepository,
)
from apps.flows.src.db.mcp_repository import MCPServerRepository
from apps.flows.src.db.operator_repository import OperatorRepository
from apps.flows.src.durable_execution import (
    DurableWorkflowRepository,
    DurableWorkflowRuntime,
)
from apps.flows.src.evaluation.service import EvaluationService
from apps.flows.src.models import TriggerType
from apps.flows.src.registry.nodes import NodeRegistry, create_default_node_registry
from apps.flows.src.runners.remote import RemoteCodeRunner
from apps.flows.src.services.flow_discovery import FlowDiscoveryService
from apps.flows.src.services.flow_factory import FlowFactory
from apps.flows.src.services.lara_action_engine import LaraActionEngine
from apps.flows.src.services.lara_facade import LaraFacade
from apps.flows.src.services.llm_models_service import LLMModelsService
from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
from apps.flows.src.services.resource_loader import ResourceLoader
from apps.flows.src.services.schedule_service import ScheduleService
from apps.flows.src.tools.base import BaseTool
from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper
from apps.flows.src.tools.registry import ToolRegistry
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.registry import TriggerRegistry
from apps.flows.src.variables import VariablesService
from core.capabilities import CAPABILITY_LANGUAGE_SET
from core.clients.a2a_client import A2AClient
from core.clients.loki_client import LokiClient
from core.clients.redis_client import RedisClient
from core.clients.tempo_client import TempoClient
from core.compiler import GraphCompiler
from core.config.testing import is_testing
from core.container import BaseContainer, lazy
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.logging import get_logger
from core.scheduler import SchedulerTaskRepository

if TYPE_CHECKING:
    from apps.flows.src.channels.a2a import A2AChannel

logger = get_logger(__name__)


class FlowContainer(BaseContainer):
    """DI контейнер сервиса flows."""

    # Флаг выполнения через воркер.
    # True = kiq() отправляет в воркер
    # False = kiq() выполняет локально (внутри воркера)
    use_worker: bool = True

    def _runtime_contract(self) -> FlowRuntimeContainer:
        return as_flow_runtime_container(self)

    @lazy
    def flow_repository(self) -> FlowRepository:
        return FlowRepository(storage=self.storage)

    @lazy
    def node_repository(self) -> NodeRepository:
        return NodeRepository(storage=self.storage)

    @lazy
    def tool_repository(self) -> ToolRepository:
        return ToolRepository(storage=self.storage)

    @lazy
    def durable_workflow_repository(self) -> DurableWorkflowRepository:
        return DurableWorkflowRepository(storage=self.storage)

    @lazy
    def workflow_runtime(self) -> DurableWorkflowRuntime:
        return DurableWorkflowRuntime(
            repository=self.durable_workflow_repository,
            redis_client=self.redis_client,
        )

    @lazy
    def redis_client(self) -> RedisClient:
        settings = get_settings()
        redis_url = settings.database.redis_url
        client = RedisClient(redis_url)
        return client

    @lazy
    def evaluation_repository(self) -> EvaluationRepository:
        return EvaluationRepository(storage=self.storage)

    # push_subscription_repository наследуется из BaseContainer (core/push/)

    @lazy
    def scheduler_task_repository(self) -> SchedulerTaskRepository:
        """
        Платформенный scheduler repository (shared БД).

        Живёт в core/scheduler/. Используется TaskIQ-задачами flows для
        обновления статуса выполнения scheduled tasks без import-зависимости
        от apps/scheduler/container.
        """
        settings = get_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url обязателен для scheduler_task_repository")
        return SchedulerTaskRepository(db_url=settings.database.shared_url)

    @lazy
    def mcp_server_repository(self) -> MCPServerRepository:
        return MCPServerRepository(storage=self.storage)

    @lazy
    def resource_repository(self) -> ResourceRepository:
        return ResourceRepository(storage=self.storage)

    @lazy
    def operator_repository(self) -> OperatorRepository:
        return OperatorRepository(storage=self.storage)

    @lazy
    def operator_handoff_service(self) -> OperatorHandoffService:
        return OperatorHandoffService(
            repository=self.operator_repository,
            file_repository=self.file_repository,
            redis_client=self.redis_client,
            workflow_runtime=self.workflow_runtime,
        )

    # rag_repository наследуется из BaseContainer (core/container/base.py)

    @lazy
    def variables_service(self) -> VariablesService:
        return VariablesService(self.variable_repository)

    @lazy
    def evaluation_service(self) -> EvaluationService:
        return EvaluationService(
            evaluation_repository=self.evaluation_repository,
            flow_repository=self.flow_repository,
            flow_factory=self.flow_factory,
            node_registry=self.node_registry,
            node_repository=self.node_repository,
            tool_registry=self.tool_registry,
        )

    # push сервис перенесен в core/push/service.py и инициализируется в factory.py

    @lazy
    def schedule_service(self) -> ScheduleService:
        return ScheduleService(
            scheduler_client=self.scheduler_client,
            scheduler_service=None,
        )

    @lazy
    def tempo_client(self) -> TempoClient:
        settings = get_settings()
        return TempoClient(base_url=settings.tracing.tempo_http_url)

    @lazy
    def loki_client(self) -> LokiClient | None:
        settings = get_settings()
        base = settings.logging.resolve_loki_query_http_base()
        if not base:
            return None
        return LokiClient(base_url=base)

    @lazy
    def a2a_client(self) -> A2AClient:
        return A2AClient()

    @lazy
    def flow_discovery(self) -> FlowDiscoveryService:
        return FlowDiscoveryService(
            repository=self.flow_repository,
            a2a_client=self.a2a_client,
        )

    @lazy
    def node_registry(self) -> NodeRegistry:
        return create_default_node_registry()

    @lazy
    def tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry(
            container=self._runtime_contract(),
            node_tool_wrapper_cls=NodeAsToolWrapper,
        )
        registry.register_builtin_tools()
        return registry

    @lazy
    def graph_compiler(self) -> GraphCompiler:
        return GraphCompiler()

    @lazy
    def base_tool_class(self) -> type[BaseTool]:
        return BaseTool

    @lazy
    def python_code_runner(self) -> RemoteCodeRunner:
        """Stateless remote Python runner для валидации кода."""
        return RemoteCodeRunner("python")

    def get_code_runner(
        self,
        language: str = "python",
    ) -> RemoteCodeRunner:
        """Возвращает runner для указанного языка."""
        if language in CAPABILITY_LANGUAGE_SET:
            return RemoteCodeRunner(language)
        raise ValueError(f"Unsupported language: {language}")

    @lazy
    def resource_loader(self) -> ResourceLoader:
        return ResourceLoader(
            node_registry=self.node_registry,
            tool_registry=self.tool_registry,
            flow_repository=self.flow_repository,
            node_repository=self.node_repository,
            tool_repository=self.tool_repository,
            container=self._runtime_contract(),
        )

    @lazy
    def llm_model_repository(self) -> LLMModelRepository:
        return LLMModelRepository(storage=self.storage)

    @lazy
    def llm_models_service(self) -> LLMModelsService:
        return LLMModelsService(
            repository=self.llm_model_repository,
            scheduler_client=self.scheduler_client,
        )

    @lazy
    def lara_action_engine(self) -> LaraActionEngine:
        return LaraActionEngine(redis_client=self.redis_client)

    @lazy
    def lara_facade(self) -> LaraFacade:
        return LaraFacade(action_engine=self.lara_action_engine)

    @lazy
    def flow_factory(self) -> FlowFactory:
        return FlowFactory(
            flow_repository=self.flow_repository,
            variables_service=self.variables_service,
            graph_compiler=self.graph_compiler,
            container=self._runtime_contract(),
        )

    @lazy
    def trigger_registry(self) -> TriggerRegistry:
        settings = get_settings()
        base_url = settings.server.get_flows_webhook_public_base_url()

        registry = TriggerRegistry(base_url=base_url, container=self._runtime_contract())

        # Регистрируем handlers
        registry.register_handler(TriggerType.TELEGRAM, TelegramTriggerHandler)

        return registry

    @lazy
    def channel_registry(self) -> ChannelRegistry:
        return create_default_channel_registry()

    @lazy
    def embed_mapping_repository(self) -> EmbedMappingRepository:
        """Репозиторий для глобального маппинга embed_id -> company_id"""
        return EmbedMappingRepository(storage=self.shared_storage)

    @lazy
    def embed_config_repository(self) -> EmbedConfigRepository:
        """Репозиторий для конфигураций встраиваемых виджетов"""
        return EmbedConfigRepository(storage=self.shared_storage)

    def get_channel(self, name: str, flow_id: str) -> A2AChannel:
        return build_channel(name, flow_id, container=self._runtime_contract())


def get_container() -> FlowContainer:
    """Получает контейнер (создает при первом вызове)."""
    current = get_current_container()
    if current is None:
        settings = get_settings()
        container = FlowContainer(
            db_url=settings.database.flows_url,
            shared_db_url=settings.database.shared_url,
        )
        # В тестах по умолчанию без воркера
        if is_testing():
            container.use_worker = False
        set_current_container(as_flow_runtime_container(container))
        logger.info("FlowContainer создан")
        return container
    return cast(FlowContainer, cast(object, current))


def set_container(container: FlowContainer) -> None:
    """Устанавливает контейнер (для тестов)."""
    set_current_container(as_flow_runtime_container(container))


def reset_container() -> None:
    """Сбрасывает контейнер."""
    reset_current_container()
