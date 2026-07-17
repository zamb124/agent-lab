"""REST API групп инструментов HumanitecAgent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.agent.device_auth import (
    extract_device_id_from_bearer,
    reject_revoked_device_bearer_if_present,
)
from apps.agent.service import (
    build_toolkit_mcp_url_for_frontend,
    resolve_brand_frontend_base_url,
    resolve_frontend_base_url,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.agent_toolkit import AgentToolkit
from apps.flows.src.services.agent_toolkit_notify import notify_agent_toolkits_updated
from apps.flows.src.services.agent_toolkit_service import (
    CUSTOM_TOOLKIT_SOURCE,
    delete_agent_toolkit,
    ensure_agent_toolkits_bootstrapped,
    get_agent_toolkit,
    list_agent_toolkits,
    save_agent_toolkit,
)
from core.context import require_context
from core.models import StrictBaseModel

router = APIRouter(tags=["agent-toolkits"])

_LINNEX_AGENT_DESKTOP_TOOLKIT_ID = "lara"


class AgentToolkitResponse(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool
    position: int
    flow_ids: list[str]
    tool_ids: list[str]
    source: str
    mcp_url: str | None = None


class AgentToolkitCatalogItem(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool
    position: int
    mcp_url: str


class AgentToolkitCreateRequest(StrictBaseModel):
    toolkit_id: str
    name: str
    description: str
    default_enabled: bool = False
    position: int = 100
    flow_ids: list[str] = []
    tool_ids: list[str] = []


class AgentToolkitUpdateRequest(StrictBaseModel):
    name: str
    description: str
    default_enabled: bool
    position: int
    flow_ids: list[str]
    tool_ids: list[str]


def _to_response(toolkit: AgentToolkit, *, mcp_url: str | None = None) -> AgentToolkitResponse:
    return AgentToolkitResponse(
        toolkit_id=toolkit.toolkit_id,
        name=toolkit.name,
        description=toolkit.description,
        default_enabled=toolkit.default_enabled,
        position=toolkit.position,
        flow_ids=list(toolkit.flow_ids),
        tool_ids=list(toolkit.tool_ids),
        source=toolkit.source,
        mcp_url=mcp_url,
    )


def _require_company_id() -> str:
    context = require_context()
    active_company = context.active_company
    if active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    return active_company.company_id


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
async def list_agent_toolkits_manage(container: ContainerDep) -> list[AgentToolkitResponse]:
    _ = require_context()
    items: list[AgentToolkitResponse] = []
    for toolkit in await list_agent_toolkits(container.agent_toolkit_repository):
        items.append(_to_response(toolkit))
    return items


@router.get("/agent/toolkits/manage/{toolkit_id}")
async def get_agent_toolkit_manage(
    toolkit_id: str,
    container: ContainerDep,
) -> AgentToolkitResponse:
    _ = require_context()
    toolkit = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    if toolkit is None:
        raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
    return _to_response(toolkit)


@router.post("/agent/toolkits/manage")
async def create_agent_toolkit(
    request_body: AgentToolkitCreateRequest,
    container: ContainerDep,
) -> AgentToolkitResponse:
    _ = require_context()
    existing = await get_agent_toolkit(
        container.agent_toolkit_repository,
        request_body.toolkit_id,
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Toolkit {request_body.toolkit_id!r} уже существует")
    toolkit = AgentToolkit(
        toolkit_id=request_body.toolkit_id,
        name=request_body.name,
        description=request_body.description,
        default_enabled=request_body.default_enabled,
        position=request_body.position,
        flow_ids=list(request_body.flow_ids),
        tool_ids=list(request_body.tool_ids),
        source=CUSTOM_TOOLKIT_SOURCE,
    )
    saved = await save_agent_toolkit(container.agent_toolkit_repository, toolkit)
    await notify_agent_toolkits_updated(container.redis_client, _require_company_id())
    return _to_response(saved)


@router.put("/agent/toolkits/manage/{toolkit_id}")
async def update_agent_toolkit(
    toolkit_id: str,
    request_body: AgentToolkitUpdateRequest,
    container: ContainerDep,
) -> AgentToolkitResponse:
    _ = require_context()
    existing = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
    updated = existing.model_copy(
        update={
            "name": request_body.name,
            "description": request_body.description,
            "default_enabled": request_body.default_enabled,
            "position": request_body.position,
            "flow_ids": list(request_body.flow_ids),
            "tool_ids": list(request_body.tool_ids),
        }
    )
    saved = await save_agent_toolkit(container.agent_toolkit_repository, updated)
    await notify_agent_toolkits_updated(container.redis_client, _require_company_id())
    return _to_response(saved)


@router.delete("/agent/toolkits/manage/{toolkit_id}")
async def remove_agent_toolkit(
    toolkit_id: str,
    container: ContainerDep,
) -> dict[str, bool]:
    _ = require_context()
    existing = await get_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Toolkit {toolkit_id!r} не найден")
    if existing.source == "platform":
        raise HTTPException(status_code=403, detail="Platform toolkit нельзя удалить")
    await delete_agent_toolkit(container.agent_toolkit_repository, toolkit_id)
    await notify_agent_toolkits_updated(container.redis_client, _require_company_id())
    return {"removed": True}
