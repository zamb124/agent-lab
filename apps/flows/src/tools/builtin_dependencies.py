"""Process-клиенты builtin tools. Сопоставление с параметром — по типу, не по имени."""

from __future__ import annotations

from typing import TypeAlias

from apps.flows.src.services.device_client import DeviceClient
from apps.flows.src.services.flow_schedule_client import FlowScheduleClient
from apps.flows.src.services.flows_client import FlowsClient
from apps.flows.src.services.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.services.hitl_client import HitlClient
from apps.flows.src.services.hitl_work_item_service import HitlWorkItemService
from apps.flows.src.services.lara_client import LaraClient
from apps.flows.src.services.lara_facade import LaraFacade
from apps.flows.src.services.schedule_service import ScheduleService
from apps.flows.src.services.tool_approval import ToolApprovalStore
from core.clients.redis_client import RedisClient
from core.clients.worktracker_client import WorktrackerClient
from core.integrations.company_credentials import CompanyIntegrationCredentialService
from core.integrations.oauth_service import OAuthService
from core.worktracker.service import WorkItemService

BuiltinToolClient: TypeAlias = (
    WorktrackerClient
    | FlowScheduleClient
    | HitlClient
    | DeviceClient
    | GoogleWorkspaceClient
    | FlowsClient
    | LaraClient
)


def builtin_tool_clients(
    *,
    work_item_service: WorkItemService,
    schedule_service: ScheduleService,
    hitl_work_item_service: HitlWorkItemService,
    redis_client: RedisClient,
    oauth_service: OAuthService,
    company_credentials: CompanyIntegrationCredentialService,
    lara_facade: LaraFacade,
    tool_approval_store: ToolApprovalStore,
) -> tuple[BuiltinToolClient, ...]:
    """Собирает клиенты из уже выбранных process-сервисов."""
    return (
        WorktrackerClient(work_item_service),
        FlowScheduleClient(schedule_service),
        HitlClient(hitl_work_item_service),
        DeviceClient(redis_client),
        GoogleWorkspaceClient(
            oauth_service=oauth_service,
            company_credentials=company_credentials,
        ),
        FlowsClient(
            lara_facade=lara_facade,
            tool_approval_store=tool_approval_store,
        ),
        LaraClient(lara_facade),
    )
