"""REST API групп инструментов HumanitecAgent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.agent.service import (
    build_toolkit_mcp_url_for_frontend,
    resolve_brand_frontend_base_url,
    resolve_frontend_base_url,
)
from apps.flows.realtime.agent_toolkit_operations import (
    op_flows_agent_toolkits_create,
    op_flows_agent_toolkits_item,
    op_flows_agent_toolkits_list,
    op_flows_agent_toolkits_remove,
    op_flows_agent_toolkits_update,
)
from apps.flows.realtime.operations import FlowsEmptyPayload
from apps.flows.src.agent.device_auth import (
    extract_device_id_from_bearer,
    reject_revoked_device_bearer_if_present,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.agent_toolkit import (
    AgentToolkit,
    AgentToolkitCreateRequest,
    AgentToolkitDeletedResponse,
    AgentToolkitIdPayload,
    AgentToolkitUpdatePayload,
    AgentToolkitUpdateRequest,
)
from apps.flows.src.services.agent_toolkit_service import (
    ensure_agent_toolkits_bootstrapped,
    list_agent_toolkits,
)
from core.context import require_context
from core.models import StrictBaseModel
from core.pagination import ListResponse

router = APIRouter(tags=["agent-toolkits"])

_LINNEX_AGENT_DESKTOP_TOOLKIT_ID = "lara"


class AgentToolkitCatalogItem(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool
    position: int
    mcp_url: str


@router.get("/agent/toolkits", tags=["agent-toolkits", "public"])
async def list_agent_toolkits_catalog(
    request: Request,
    container: ContainerDep,
) -> list[AgentToolkitCatalogItem]:
    await reject_revoked_device_bearer_if_present(request, container)
    context = require_context()
    active_company = context.active_company
    if active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    _ = await ensure_agent_toolkits_bootstrapped(
        container.agent_toolkit_repository,
        company_id=active_company.company_id,
    )
    request_host = request.headers.get("host")
    brand_base = resolve_brand_frontend_base_url(request_host)
    frontend_base = (
        brand_base
        if brand_base is not None
        else resolve_frontend_base_url(
            request_host=request_host,
            url_scheme=request.url.scheme,
        )
    )
    # LaraOnly: paired desktop sees only the Lara toolkit extension.
    desktop_device_id = extract_device_id_from_bearer(request)
    items: list[AgentToolkitCatalogItem] = []
    for toolkit in await list_agent_toolkits(container.agent_toolkit_repository):
        if desktop_device_id is not None and toolkit.toolkit_id != _LINNEX_AGENT_DESKTOP_TOOLKIT_ID:
            continue
        # LaraOnly: desktop must always get platform_lara ON, even if company DB
        # still has a stale default_enabled=false from an older bootstrap.
        catalog_default_enabled = (
            True
            if toolkit.toolkit_id == _LINNEX_AGENT_DESKTOP_TOOLKIT_ID
            else toolkit.default_enabled
        )
        items.append(
            AgentToolkitCatalogItem(
                toolkit_id=toolkit.toolkit_id,
                name=toolkit.name,
                description=toolkit.description,
                default_enabled=catalog_default_enabled,
                position=toolkit.position,
                mcp_url=build_toolkit_mcp_url_for_frontend(toolkit.toolkit_id, frontend_base),
            )
        )
    return items


@router.get("/agent/toolkits/manage")
async def list_agent_toolkits_manage(container: ContainerDep) -> ListResponse[AgentToolkit]:
    return await op_flows_agent_toolkits_list(
        FlowsEmptyPayload(),
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
