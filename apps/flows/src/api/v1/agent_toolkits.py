"""REST API групп инструментов HumanitecAgent."""

from __future__ import annotations

from fastapi import APIRouter, Request

from apps.agent.service import (
    resolve_brand_frontend_base_url,
    resolve_frontend_base_url,
)
from apps.flows.realtime.agent_toolkit_operations import (
    op_flows_agent_toolkits_catalog_list,
    op_flows_agent_toolkits_create,
    op_flows_agent_toolkits_item,
    op_flows_agent_toolkits_list,
    op_flows_agent_toolkits_remove,
    op_flows_agent_toolkits_update,
)
from apps.flows.src.agent.device_auth import (
    extract_device_id_from_bearer,
    reject_revoked_device_bearer_if_present,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.agent_toolkit import (
    AgentToolkit,
    AgentToolkitCatalogItem,
    AgentToolkitCatalogListPayload,
    AgentToolkitCreateRequest,
    AgentToolkitDeletedResponse,
    AgentToolkitIdPayload,
    AgentToolkitUpdatePayload,
    AgentToolkitUpdateRequest,
)
from core.context import require_context
from core.pagination import ListResponse
from core.websocket import EmptyPayload

router = APIRouter(tags=["agent-toolkits"])

@router.get("/agent/toolkits", tags=["agent-toolkits", "public"])
async def list_agent_toolkits_catalog(
    request: Request,
    container: ContainerDep,
) -> ListResponse[AgentToolkitCatalogItem]:
    await reject_revoked_device_bearer_if_present(request, container)
    request_host = request.headers.get("host")
    brand_base = resolve_brand_frontend_base_url(request_host)
    frontend_base = (
        brand_base
        if brand_base is not None
        else resolve_frontend_base_url(request_host=request_host, url_scheme=request.url.scheme)
    )
    return await op_flows_agent_toolkits_catalog_list(
        AgentToolkitCatalogListPayload(
            frontend_base_url=frontend_base,
            desktop_only=extract_device_id_from_bearer(request) is not None,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/agent/toolkits/manage")
async def list_agent_toolkits_manage(container: ContainerDep) -> ListResponse[AgentToolkit]:
    return await op_flows_agent_toolkits_list(
        EmptyPayload(),
        user=require_context().user,
        container=container,
    )


@router.get("/agent/toolkits/manage/{toolkit_id}")
async def get_agent_toolkit_manage(
    toolkit_id: str,
    container: ContainerDep,
) -> AgentToolkit:
    return await op_flows_agent_toolkits_item(
        AgentToolkitIdPayload(toolkit_id=toolkit_id),
        user=require_context().user,
        container=container,
    )


@router.post("/agent/toolkits/manage")
async def create_agent_toolkit(
    request_body: AgentToolkitCreateRequest,
    container: ContainerDep,
) -> AgentToolkit:
    return await op_flows_agent_toolkits_create(
        request_body,
        user=require_context().user,
        container=container,
    )


@router.put("/agent/toolkits/manage/{toolkit_id}")
async def update_agent_toolkit(
    toolkit_id: str,
    request_body: AgentToolkitUpdateRequest,
    container: ContainerDep,
) -> AgentToolkit:
    return await op_flows_agent_toolkits_update(
        AgentToolkitUpdatePayload.model_validate(
            {"toolkit_id": toolkit_id, **request_body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/agent/toolkits/manage/{toolkit_id}")
async def remove_agent_toolkit(
    toolkit_id: str,
    container: ContainerDep,
) -> AgentToolkitDeletedResponse:
    return await op_flows_agent_toolkits_remove(
        AgentToolkitIdPayload(toolkit_id=toolkit_id),
        user=require_context().user,
        container=container,
    )
