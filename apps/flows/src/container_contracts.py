"""Structural contracts for flows runtime dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypedDict, cast

from core.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from apps.flows.src.db import (
        DatabaseStateRepository,
        EvaluationRepository,
        FlowRepository,
        LLMModelRepository,
        NodeRepository,
        ResourceRepository,
        ScheduledTaskRepository,
        ToolRepository,
    )
    from apps.flows.src.db.mcp_repository import MCPServerRepository
    from apps.flows.src.db.operator_repository import OperatorRepository
    from apps.flows.src.models import (
        BranchConfig,
        FlowConfig,
        NodeConfig,
        ResourceMapInput,
        ToolReference,
        TriggerConfig,
    )
    from apps.flows.src.models.enums import ChannelType, NodeType
    from apps.flows.src.models.evaluation_result import EvaluationServiceStreamEvent
    from apps.flows.src.models.flow_config import Edge
    from apps.flows.src.models.registry_contracts import RegistryFlowSchema
    from apps.flows.src.runners.remote import RemoteCodeRunner
    from apps.flows.src.services.flow_discovery import FlowDiscoveryService
    from apps.flows.src.services.lara_action_engine import LaraActionEngine
    from apps.flows.src.services.lara_facade import LaraFacade
    from apps.flows.src.services.llm_models_service import LLMModelsService
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
    from apps.flows.src.services.schedule_service import ScheduleService
    from apps.flows.src.state import StateManager
    from apps.flows.src.tools.base import BaseTool
    from apps.flows.src.variables import VariablesService
    from core.billing import BillingService
    from core.clients.a2a_client import A2AClient
    from core.clients.loki_client import LokiClient
    from core.clients.redis_client import RedisClient
    from core.clients.tempo_client import TempoClient
    from core.compiler import GraphCompiler
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.embed_config_repository import EmbedConfigRepository
    from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
    from core.db.repositories.user_repository import UserRepository
    from core.db.repositories.variable_repository import VariableRepository
    from core.files.file_repository import FileRepository
    from core.files.processors import FileProcessor
    from core.integrations.oauth_service import OAuthService
    from core.rag.llm_context_memory_store import RAGLLMContextMemoryStore
    from core.rag.repository import RAGRepository
    from core.state import ExecutionState
    from core.text_transforms import TextTransformService


class _FlowRuntimeContainerSource(Protocol):
    pass


def as_flow_runtime_container(container: _FlowRuntimeContainerSource) -> FlowRuntimeContainer:
    return cast(FlowRuntimeContainer, container)


class EffectiveFlowConfig(TypedDict):
    entry: str | None
    nodes: dict[str, "FlowNodeRuntimeConfig"]
    edges: list[Edge]
    variables: JsonObject


FlowNodeRuntimeConfig: TypeAlias = JsonObject


class RuntimeFlowConfig(TypedDict, total=False):
    version: JsonValue
    nodes: dict[str, FlowNodeRuntimeConfig]


class RuntimeFlowProtocol(Protocol):
    variables: JsonObject
    config: RuntimeFlowConfig
    nodes: dict[str, "RuntimeNodeProtocol"]
    run: Callable[["ExecutionState"], Awaitable["ExecutionState"]]


class RuntimeNodeProtocol(Protocol):
    config: FlowNodeRuntimeConfig
    run: Callable[["ExecutionState"], Awaitable["ExecutionState"]]


class RuntimeNodeClassProtocol(Protocol):
    def from_config(
        self,
        node_id: str,
        config: Mapping[str, JsonValue],
    ) -> RuntimeNodeProtocol: ...


class NodeRegistryProtocol(Protocol):
    def get(self, key: str | NodeType) -> RuntimeNodeClassProtocol: ...


class ToolRegistryProtocol(Protocol):
    def get(self, name: str) -> BaseTool | None: ...

    def register_builtin_tools(self) -> None: ...

    async def materialize(
        self,
        tool_ref: JsonObject | ToolReference | NodeConfig,
    ) -> BaseTool: ...

    async def create_tool(
        self,
        tool_ref: str | JsonObject | ToolReference | NodeConfig,
    ) -> BaseTool: ...

    async def create_tools(
        self, tool_refs: Sequence[str | JsonObject | ToolReference | NodeConfig],
    ) -> list[BaseTool]: ...


class ChannelActionHandlerProtocol(Protocol):
    async def execute_action(
        self,
        action: str,
        params: Mapping[str, JsonValue],
        config: Mapping[str, JsonValue],
        variables: Mapping[str, JsonValue],
    ) -> JsonObject: ...


class ChannelRegistryProtocol(Protocol):
    def get(self, channel_type: ChannelType | str) -> ChannelActionHandlerProtocol: ...


class FlowFactoryProtocol(Protocol):
    @property
    def container(self) -> "FlowRuntimeContainer": ...

    async def get_flow_config_snapshot(
        self,
        flow_id: str,
        config_version: str | None = None,
    ) -> FlowConfig | None: ...

    async def get_flow(
        self,
        flow_id: str,
        branch_id: str = "default",
        config_version: str | None = None,
    ) -> RuntimeFlowProtocol | None: ...

    async def get_resource_maps(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> tuple[ResourceMapInput, ResourceMapInput | None]: ...

    async def get_effective_nodes_map(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> dict[str, FlowNodeRuntimeConfig]: ...

    async def get_resolved_variables_map(
        self,
        flow_id: str,
        branch_id: str = "default",
        *,
        config_version: str | None = None,
    ) -> JsonObject: ...

    async def create_validation_flow(
        self,
        config: Mapping[str, JsonValue],
    ) -> RuntimeFlowProtocol: ...

    def apply_branch(self, config: FlowConfig, branch_id: str) -> EffectiveFlowConfig: ...

    async def get_branches(self, flow_id: str) -> dict[str, BranchConfig]: ...

    async def get_flow_schema(self, flow_id: str) -> RegistryFlowSchema | None: ...


class FlowEvaluationFactoryProtocol(Protocol):
    @property
    def container(self) -> "FlowRuntimeContainer": ...

    async def get_effective_nodes_map(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> dict[str, FlowNodeRuntimeConfig]: ...


class TriggerRegistryProtocol(Protocol):
    async def sync_triggers(
        self,
        flow_id: str,
        old_config: FlowConfig | None,
        new_config: FlowConfig,
    ) -> FlowConfig: ...

    async def reregister_trigger(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig: ...


class EvaluationServiceProtocol(Protocol):
    def run_test_stream(
        self,
        flow_id: str,
        branch_id: str,
        test_case_id: str,
        task_id: str | None = None,
    ) -> AsyncIterator[EvaluationServiceStreamEvent]: ...


class FlowRuntimeContainer(Protocol):
    @property
    def redis_client(self) -> RedisClient: ...

    @property
    def flow_repository(self) -> FlowRepository: ...

    @property
    def flow_factory(self) -> FlowFactoryProtocol: ...

    @property
    def state_manager(self) -> StateManager: ...

    @property
    def variables_service(self) -> VariablesService: ...

    @property
    def resource_repository(self) -> ResourceRepository: ...

    @property
    def rag_repository(self) -> RAGRepository: ...

    @property
    def llm_context_memory_store(self) -> RAGLLMContextMemoryStore: ...

    @property
    def text_transform_service(self) -> TextTransformService: ...

    @property
    def node_repository(self) -> NodeRepository: ...

    @property
    def tool_repository(self) -> ToolRepository: ...

    @property
    def tool_registry(self) -> ToolRegistryProtocol: ...

    @property
    def mcp_server_repository(self) -> MCPServerRepository: ...

    @property
    def channel_registry(self) -> ChannelRegistryProtocol: ...

    @property
    def operator_repository(self) -> OperatorRepository: ...

    @property
    def operator_handoff_service(self) -> OperatorHandoffService: ...

    @property
    def a2a_client(self) -> A2AClient: ...

    @property
    def flow_discovery(self) -> FlowDiscoveryService: ...

    @property
    def billing_service(self) -> BillingService: ...

    @property
    def file_processor(self) -> FileProcessor: ...

    @property
    def evaluation_service(self) -> EvaluationServiceProtocol: ...

    @property
    def base_tool_class(self) -> type[BaseTool]: ...

    def get_code_runner(
        self,
        language: str = "python",
    ) -> RemoteCodeRunner: ...

    @property
    def schedule_service(self) -> ScheduleService: ...

    @property
    def oauth_service(self) -> OAuthService: ...

    @property
    def lara_facade(self) -> LaraFacade: ...

    @property
    def file_repository(self) -> FileRepository: ...

    @property
    def state_repository(self) -> DatabaseStateRepository: ...

    @property
    def scheduled_task_repository(self) -> ScheduledTaskRepository: ...

    @property
    def evaluation_repository(self) -> EvaluationRepository: ...

    @property
    def node_registry(self) -> NodeRegistryProtocol: ...

    @property
    def graph_compiler(self) -> GraphCompiler: ...

    @property
    def llm_model_repository(self) -> LLMModelRepository: ...

    @property
    def llm_models_service(self) -> LLMModelsService: ...

    @property
    def lara_action_engine(self) -> LaraActionEngine: ...

    @property
    def trigger_registry(self) -> TriggerRegistryProtocol: ...

    @property
    def tempo_client(self) -> TempoClient: ...

    @property
    def loki_client(self) -> LokiClient | None: ...

    @property
    def embed_mapping_repository(self) -> EmbedMappingRepository: ...

    @property
    def embed_config_repository(self) -> EmbedConfigRepository: ...

    @property
    def company_repository(self) -> CompanyRepository: ...

    @property
    def user_repository(self) -> UserRepository: ...

    @property
    def variable_repository(self) -> VariableRepository: ...
