"""ChannelFactory — создание каналов по имени."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from apps.flows.src.a2a.task_projection_service import A2ATaskProjectionService
from apps.flows.src.contracts import (
    ChannelRegistryProtocol,
    FlowFactoryProtocol,
    ToolRegistryProtocol,
)
from apps.flows.src.durable_execution import DurableWorkflowRuntime
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flow_ui_share_service import FlowUIShareService
from apps.flows.src.services.handoff_orchestrator_service import HandoffOrchestratorService
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from core.authz.service import AuthzService
from core.clients.redis_client import RedisClient
from core.db.storage import Storage
from core.files.service import FilesService
from core.mail.service import MailService
from core.models.context_models import Context
from core.variables.service import VariablesService

if TYPE_CHECKING:
    from apps.flows.src.channels.a2a import A2AChannel

ChannelT = TypeVar("ChannelT", bound="ChannelClass")


class ChannelClass(Protocol):
    name: str

    def __call__(
        self,
        flow_id: str,
        context: Context | None = None,
        flow_config: FlowConfig | None = None,
        *,
        variables_service: VariablesService,
        authz_service: AuthzService,
        workflow_runtime: DurableWorkflowRuntime,
        redis_client: RedisClient,
        handoff_orchestrator_service: HandoffOrchestratorService,
        flow_factory: FlowFactoryProtocol,
        tool_registry: ToolRegistryProtocol,
        projection_service: A2ATaskProjectionService,
        shared_storage: Storage,
        channel_registry: ChannelRegistryProtocol,
        mail_service: MailService,
        flow_ui_share_service: FlowUIShareService,
        hitl_conversation_service: HitlConversationService,
        files_service: FilesService,
    ) -> A2AChannel: ...


_CHANNEL_REGISTRY: dict[str, str] = {
    "a2a": "apps.flows.src.channels.a2a:A2AChannel",
    "telegram": "apps.flows.src.channels.trigger_telegram_channel:TelegramInboundChannel",
    "websocket": "apps.flows.src.channels.websocket:WebSocketChannel",
}


def _load_channel_class(path: str) -> ChannelClass:
    module_path, class_name = path.split(":", 1)
    module = importlib.import_module(module_path)
    module_attrs = cast(Mapping[str, object], vars(module))
    cls = module_attrs.get(class_name)
    if cls is None:
        raise ValueError(f"Channel class not found: {path}")
    return cast(ChannelClass, cls)


def register_channel(channel_class: type[ChannelT]) -> type[ChannelT]:
    """Декоратор для регистрации канала."""
    _CHANNEL_REGISTRY[channel_class.name] = (
        f"{channel_class.__module__}:{channel_class.__qualname__}"
    )
    return channel_class


def get_channel(
    name: str,
    flow_id: str,
    context: Context | None = None,
    flow_config: FlowConfig | None = None,
    *,
    variables_service: VariablesService,
    authz_service: AuthzService,
    workflow_runtime: DurableWorkflowRuntime,
    redis_client: RedisClient,
    handoff_orchestrator_service: HandoffOrchestratorService,
    flow_factory: FlowFactoryProtocol,
    tool_registry: ToolRegistryProtocol,
    projection_service: A2ATaskProjectionService,
    shared_storage: Storage,
    channel_registry: ChannelRegistryProtocol,
    mail_service: MailService,
    flow_ui_share_service: FlowUIShareService,
    hitl_conversation_service: HitlConversationService,
    files_service: FilesService,
) -> A2AChannel:
    """Получить канал по имени."""
    if name not in _CHANNEL_REGISTRY:
        raise ValueError(f"Unknown channel: {name}. Available: {list(_CHANNEL_REGISTRY.keys())}")

    channel_class = _load_channel_class(_CHANNEL_REGISTRY[name])
    return channel_class(
        flow_id,
        context=context,
        flow_config=flow_config,
        variables_service=variables_service,
        authz_service=authz_service,
        workflow_runtime=workflow_runtime,
        redis_client=redis_client,
        handoff_orchestrator_service=handoff_orchestrator_service,
        flow_factory=flow_factory,
        tool_registry=tool_registry,
        projection_service=projection_service,
        shared_storage=shared_storage,
        channel_registry=channel_registry,
        mail_service=mail_service,
        flow_ui_share_service=flow_ui_share_service,
        hitl_conversation_service=hitl_conversation_service,
        files_service=files_service,
    )
