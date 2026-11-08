"""DI процесса flows."""

from typing import Annotated

from apps.flows.src.a2a.task_projection_service import A2ATaskProjectionService
from apps.flows.src.channels.registry import create_default_channel_registry
from apps.flows.src.contracts import ChannelRegistryProtocol
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from apps.flows.src.evaluation.lab_service import EvaluationLabService
from apps.flows.src.models import TriggerType
from apps.flows.src.registry.nodes import NodeRegistry, create_default_node_registry
from apps.flows.src.runtime.execution_context import CodeRunnerRegistry
from apps.flows.src.runtime.llm_context_memory_store import RAGLLMContextMemoryStore
from apps.flows.src.runtime.nodes import NodeConstructor
from apps.flows.src.services.code_agent_source_service import CodeAgentSourceService
from apps.flows.src.services.code_lsp_service import CodeLspService
from apps.flows.src.services.datasources.executors import build_datasource_executors
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.flow_factory import FlowFactory
from apps.flows.src.services.flow_ui_assist_service import FlowUIAssistService
from apps.flows.src.services.flow_ui_share_service import FlowUIShareService
from apps.flows.src.services.handoff_orchestrator_service import HandoffOrchestratorService
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from apps.flows.src.services.hitl_work_item_service import HitlWorkItemService
from apps.flows.src.services.lara_action_engine import LaraActionRedisClient
from apps.flows.src.services.lara_facade import LaraFacade
from apps.flows.src.services.mcp_branding_service import MCPServerBrandingService
from apps.flows.src.services.schedule_service import ScheduleService
from apps.flows.src.services.tool_approval import ToolApprovalRedisClient, ToolApprovalStore
from apps.flows.src.services.tool_tag_group_service import ToolTagGroupService
from apps.flows.src.tools.builtin_dependencies import builtin_tool_clients
from apps.flows.src.tools.registry import ToolRegistry
from apps.flows.src.triggers.handlers.email import EmailTriggerHandler
from apps.flows.src.triggers.handlers.platform_event import PlatformEventTriggerHandler
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.handlers.webhook import WebhookTriggerHandler
from apps.flows.src.triggers.registry import TriggerRegistry
from core.ai.llm_models_service import LLMModelsService
from core.authz.service import AuthzService
from core.billing.service import BillingService
from core.clients.loki_client import LokiClient
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.clients.tempo_client import TempoClient
from core.config.models import DatabaseConfig, LoggingConfig, ServerConfig, TracingConfig
from core.config.rag_provider_factory import get_rag_provider
from core.data_tables.service import DataTableService
from core.datasources.service import DatasourceExecutors, DatasourceService
from core.db.storage import SharedStorage
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.integrations.company_credentials import CompanyIntegrationCredentialService
from core.integrations.oauth_service import OAuthService
from core.mail.service import MailService
from core.namespace.service import NamespaceService
from core.rag.base_provider import BaseRAGProvider
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.short_links.service import ShortLinkService
from core.variables.service import VariablesService
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.queue_access import WorkQueueAccessPort
from core.worktracker.service import WorkItemService


@recipe
def scheduler_client(service_client: ServiceClient) -> SchedulerClient:
    return SchedulerClient(service_client=service_client)


@recipe
def node_registry() -> NodeRegistry:
    return create_default_node_registry()


@recipe
def work_queue_access(authz: AuthzService) -> WorkQueueAccessPort:
    return WorkQueueAccessService(authz)


@recipe
def lara_action_redis(redis_client: RedisClient) -> LaraActionRedisClient:
    return redis_client


@recipe
def tool_approval_redis(redis_client: RedisClient) -> ToolApprovalRedisClient:
    return redis_client


@recipe
def rag_provider(billing_service: BillingService) -> BaseRAGProvider:
    return get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID, billing_service=billing_service)


@recipe
def channel_registry() -> ChannelRegistryProtocol:
    return create_default_channel_registry()


@recipe
def llm_context_memory_store(
    rag_provider: BaseRAGProvider,
    namespace_service: NamespaceService,
) -> RAGLLMContextMemoryStore:
    return RAGLLMContextMemoryStore(
        rag_provider=rag_provider,
        namespace_service=namespace_service,
        rag_client=RagClient(),
    )


@recipe
def tool_registry(
    work_item_service: WorkItemService,
    schedule_service: ScheduleService,
    hitl_work_item_service: HitlWorkItemService,
    oauth_service: OAuthService,
    company_credentials: CompanyIntegrationCredentialService,
    lara_facade: LaraFacade,
    tool_approval_store: ToolApprovalStore,
    node_constructor: NodeConstructor,
    flow_factory: FlowFactory,
    billing_service: BillingService,
) -> ToolRegistry:
    registry = ToolRegistry(
        clients=builtin_tool_clients(
            work_item_service=work_item_service,
            schedule_service=schedule_service,
            hitl_work_item_service=hitl_work_item_service,
            oauth_service=oauth_service,
            company_credentials=company_credentials,
            lara_facade=lara_facade,
            tool_approval_store=tool_approval_store,
            billing_service=billing_service,
        ),
        node_constructor=node_constructor,
        flow_factory=flow_factory,
    )
    registry.register_builtin_tools()
    return registry


@recipe
def datasource_executors(
    workflow_runtime: DurableWorkflowRuntime,
    flow_factory: FlowFactory,
    tool_registry: ToolRegistry,
) -> DatasourceExecutors:
    return build_datasource_executors(
        workflow_runtime=workflow_runtime,
        flow_factory=flow_factory,
        tool_registry=tool_registry,
    )


@recipe
def tempo_client(tracing: TracingConfig) -> TempoClient:
    return TempoClient(base_url=tracing.tempo_http_url)


@recipe
def loki_client(logging: LoggingConfig) -> LokiClient:
    return LokiClient(base_url=logging.resolve_loki_query_http_base())


@recipe
def trigger_registry(
    server: ServerConfig,
    flow_factory: FlowFactory,
    redis_client: RedisClient,
    mail_service: MailService,
) -> TriggerRegistry:
    base_url = server.get_flows_webhook_public_base_url()
    registry = TriggerRegistry(base_url=base_url)
    registry.register_handler(
        TriggerType.TELEGRAM, TelegramTriggerHandler(base_url, flow_factory=flow_factory)
    )
    registry.register_handler(
        TriggerType.EMAIL,
        EmailTriggerHandler(base_url, redis_client=redis_client, mail_service=mail_service),
    )
    registry.register_handler(
        TriggerType.PLATFORM_EVENT, PlatformEventTriggerHandler(base_url, redis_client=redis_client)
    )
    registry.register_handler(TriggerType.WEBHOOK, WebhookTriggerHandler(base_url))
    return registry


class FlowsDi(
    PlatformDi,
    recipes=(
        work_queue_access,
        lara_action_redis,
        tool_approval_redis,
        rag_provider,
        scheduler_client,
        node_registry,
        channel_registry,
        llm_context_memory_store,
        tool_registry,
        datasource_executors,
        tempo_client,
        loki_client,
        trigger_registry,
    ),
):
    shared_storage: SharedStorage
    service_client: ServiceClient
    tool_registry: ToolRegistry
    tool_tag_group_service: ToolTagGroupService
    node_constructor: NodeConstructor
    code_runners: CodeRunnerRegistry
    code_agent_source_service: CodeAgentSourceService
    code_lsp_service: CodeLspService
    data_table_service: DataTableService
    database: DatabaseConfig
    datasource_executors: DatasourceExecutors
    datasource_service: DatasourceService
    workflow_runtime: DurableWorkflowRuntime
    flow_factory: FlowFactory
    flow_access_service: FlowAccessService
    flow_ui_assist_service: FlowUIAssistService
    flow_ui_share_service: FlowUIShareService
    variables_service: VariablesService
    work_item_service: WorkItemService
    channel_registry: ChannelRegistryProtocol
    handoff_orchestrator_service: HandoffOrchestratorService
    a2a_task_projection_service: A2ATaskProjectionService
    hitl_conversation_service: HitlConversationService
    mcp_branding_service: MCPServerBrandingService
    evaluation_lab_service: EvaluationLabService
    lara_facade: LaraFacade
    llm_models_service: LLMModelsService
    loki_client: LokiClient
    short_link_service: ShortLinkService
    tempo_client: TempoClient
    trigger_registry: TriggerRegistry


Di = Annotated[FlowsDi, http_di(FlowsDi), task_di(FlowsDi)]
