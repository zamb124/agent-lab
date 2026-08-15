"""
API endpoints для MCP серверов.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.flows.src.clients.mcp_client import (
    MCPClient,
    MCPClientError,
)
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.models.mcp_branding import MCPServerBrandingResolved
from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from apps.flows.src.services.mcp_catalog_provisioner import (
    apply_catalog_entry_to_server,
    mark_server_override_locked,
    mcp_server_update_triggers_override,
)
from apps.flows.src.services.mcp_catalog_store import (
    install_catalog_entry_for_company,
    list_store_catalog_entries,
    uninstall_catalog_entry_from_company,
)
from apps.flows.src.services.mcp_server_display_order import sort_mcp_servers_for_display
from apps.flows.src.services.mcp_server_search import filter_mcp_servers_by_search
from apps.flows.src.services.mcp_sync import resolve_mcp_client_variables, sync_mcp_server_tools
from apps.flows.tools.builtin_specs import require_not_builtin_tool_id
from core.authz.models import AuthzObject
from core.context import get_context, require_active_company, require_context
from core.logging import get_logger
from core.pagination import OffsetPage
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(tags=["mcp"])


async def _require_company_member(container: ContainerDep) -> None:
    ctx = require_context()
    if ctx.active_company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    await container.authz_service.require_can_view(
        AuthzObject.company(ctx.active_company.company_id),
        user_id=ctx.user.user_id,
    )


class MCPServerCreateRequest(BaseModel):
    """Запрос на создание MCP сервера."""

    server_id: str = Field(
        ...,
        description="Уникальный ID сервера",
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        min_length=2,
        max_length=64
    )
    name: str = Field(..., description="Название сервера")
    url: str = Field(..., description="URL MCP сервера")
    transport_type: MCPTransportType = Field(
        default=MCPTransportType.HTTP,
        description="Тип транспорта"
    )
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    description: str | None = Field(default=None, description="Описание")


class MCPServerUpdateRequest(BaseModel):
    """Запрос на обновление MCP сервера."""

    name: str | None = None
    url: str | None = None
    transport_type: MCPTransportType | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None
    description: str | None = None


class MCPServerResponse(BaseModel):
    """Ответ с данными MCP сервера."""

    server_id: str
    name: str
    url: str
    transport_type: str
    headers: dict[str, str]
    is_active: bool
    cached_tools: list[str]
    last_sync_at: datetime | None
    description: str | None
    source: str
    catalog_id: str | None
    catalog_snapshot_hash: str | None
    catalog_auto_provisioned: bool
    override_locked: bool
    override_locked_at: datetime | None
    override_locked_by_user_id: str | None
    icon_url: str | None = None


class MCPServerBrandingResponse(BaseModel):
    """Глобальная иконка MCP сервера по slug."""

    server_id: str
    icon_file_id: str
    icon_url: str
    updated_at: datetime
    updated_by_user_id: str


class MCPServerBrandingUpsertRequest(BaseModel):
    """Загрузка иконки для slug."""

    icon_file_id: str = Field(..., min_length=1, description="Публичный file_id иконки")


class MCPServerBrandingSlugSuggestResponse(BaseModel):
    """Подсказки slug для branding иконок MCP."""

    slugs: list[str]


class MCPToolResponse(BaseModel):
    """Информация о tool."""

    name: str
    title: str | None
    description: str | None
    parameters_schema: JsonObject
    output_schema: JsonObject | None
    schema_hash: str
    schema_version: str


class MCPSyncResponse(BaseModel):
    """Результат синхронизации."""

    success: bool
    tools_count: int
    tools: list[MCPToolResponse]


class MCPTestResponse(BaseModel):
    """Результат теста подключения."""

    success: bool
    message: str
    tools_count: int
    transport_type: str
    url: str


class MCPCatalogStoreItemResponse(BaseModel):
    """Запись MCP Store (opt-in tier)."""

    catalog_id: str
    registry_name: str
    title: str
    description: str | None
    upstream_url: str
    transport_type: str
    auth_policy: str
    verify_status: str
    tool_count_snapshot: int
    installed: bool
    platform_curated: bool
    icon_url: str | None = None


def _server_to_response(
    server: MCPServerConfig,
    *,
    icon_url: str | None = None,
) -> MCPServerResponse:
    """Конвертирует MCPServerConfig в response."""
    return MCPServerResponse(
        server_id=server.server_id,
        name=server.name,
        url=server.url,
        transport_type=server.transport_type.value,
        headers=server.headers,
        is_active=server.is_active,
        cached_tools=server.cached_tools,
        last_sync_at=server.last_sync_at,
        description=server.description,
        source=server.source.value,
        catalog_id=server.catalog_id,
        catalog_snapshot_hash=server.catalog_snapshot_hash,
        catalog_auto_provisioned=server.catalog_auto_provisioned,
        override_locked=server.override_locked,
        override_locked_at=server.override_locked_at,
        override_locked_by_user_id=server.override_locked_by_user_id,
        icon_url=icon_url,
    )


def _branding_resolved_to_response(item: MCPServerBrandingResolved) -> MCPServerBrandingResponse:
    return MCPServerBrandingResponse(
        server_id=item.server_id,
        icon_file_id=item.icon_file_id,
        icon_url=item.icon_url,
        updated_at=item.updated_at,
        updated_by_user_id=item.updated_by_user_id,
    )


async def _server_response(
    container: ContainerDep,
    server: MCPServerConfig,
    *,
    icon_url_map: dict[str, str] | None = None,
) -> MCPServerResponse:
    if icon_url_map is None:
        icon_url = await container.mcp_branding_service.get_icon_url(server.server_id)
    else:
        icon_url = icon_url_map.get(server.server_id)
    return _server_to_response(server, icon_url=icon_url)


@router.get("/servers", response_model=OffsetPage[MCPServerResponse])
async def list_servers(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPServerResponse]:
    servers = await container.mcp_server_repository.list(limit=5000, offset=0)
    filtered_servers = filter_mcp_servers_by_search(servers, search)
    ordered_servers = sort_mcp_servers_for_display(filtered_servers)
    total = len(ordered_servers)
    page_servers = ordered_servers[offset : offset + limit]
    icon_url_map = await container.mcp_branding_service.build_icon_url_map_for_server_ids(
        [server.server_id for server in page_servers]
    )
    items = [_server_to_response(s, icon_url=icon_url_map.get(s.server_id)) for s in page_servers]
    return OffsetPage[MCPServerResponse](items=items, total=total, limit=limit, offset=offset)


@router.get("/catalog", response_model=OffsetPage[MCPCatalogStoreItemResponse])
async def list_mcp_catalog(
    container: ContainerDep,
    tier: Annotated[str, Query()] = "store",
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPCatalogStoreItemResponse]:
    if tier != "store":
        raise HTTPException(status_code=400, detail="Only tier=store is supported")

    runtime = as_flow_runtime_container(container)
    page_entries, total = await list_store_catalog_entries(
        container=runtime,
        search=search,
        limit=limit,
        offset=offset,
    )
    icon_url_map = await container.mcp_branding_service.build_icon_url_map_for_server_ids(
        [server_id_from_catalog_id(entry.catalog_id) for entry, _installed, _platform_curated in page_entries]
    )
    items = [
        MCPCatalogStoreItemResponse(
            catalog_id=entry.catalog_id,
            registry_name=entry.registry_name,
            title=entry.title,
            description=entry.description,
            upstream_url=entry.upstream_url,
            transport_type=entry.transport_type,
            auth_policy=entry.auth_policy.value,
            verify_status=entry.verify_status.value,
            tool_count_snapshot=entry.tool_count_snapshot,
            installed=installed,
            platform_curated=platform_curated,
            icon_url=icon_url_map.get(server_id_from_catalog_id(entry.catalog_id)),
        )
        for entry, installed, platform_curated in page_entries
    ]
    return OffsetPage[MCPCatalogStoreItemResponse](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/catalog/{catalog_id}/install", response_model=MCPServerResponse)
async def install_mcp_catalog_entry(
    catalog_id: str,
    container: ContainerDep,
) -> MCPServerResponse:
    await _require_company_member(container)
    runtime = as_flow_runtime_container(container)
    try:
        server = await install_catalog_entry_for_company(
            container=runtime,
            catalog_id=catalog_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=502, detail=f"MCP server error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Connection error: {exc}") from exc

    return await _server_response(container, server)


@router.delete("/catalog/{catalog_id}/install")
async def uninstall_mcp_catalog_entry(
    catalog_id: str,
    container: ContainerDep,
) -> dict[str, str]:
    await _require_company_member(container)
    runtime = as_flow_runtime_container(container)
    try:
        await uninstall_catalog_entry_from_company(
            container=runtime,
            catalog_id=catalog_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "uninstalled", "catalog_id": catalog_id}


@router.post("/servers", response_model=MCPServerResponse)
async def create_server(
    request: MCPServerCreateRequest,
    container: ContainerDep,
) -> MCPServerResponse:
    """Создает MCP сервер."""
    await _require_company_member(container)
    existing = await container.mcp_server_repository.get(request.server_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Server {request.server_id} already exists"
        )

    server = MCPServerConfig(
        server_id=request.server_id,
        name=request.name,
        url=request.url,
        transport_type=request.transport_type,
        headers=request.headers,
        description=request.description,
        source=MCPServerSource.MANUAL,
    )

    _ = await container.mcp_server_repository.set(server)
    logger.info(f"MCP server created: {request.server_id}")

    return await _server_response(container, server)


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str,
    container: ContainerDep,
) -> MCPServerResponse:
    """Получает MCP сервер по ID."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    return await _server_response(container, server)


@router.put("/servers/{server_id}", response_model=MCPServerResponse)
async def update_server(
    server_id: str,
    request: MCPServerUpdateRequest,
    container: ContainerDep,
) -> MCPServerResponse:
    """Обновляет MCP сервер."""
    await _require_company_member(container)
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    next_transport = (
        MCPTransportType(request.transport_type)
        if request.transport_type is not None
        else None
    )
    triggers_override = mcp_server_update_triggers_override(
        server=server,
        name=request.name,
        url=request.url,
        transport_type=next_transport,
        headers=request.headers,
        description=request.description,
        is_active=request.is_active,
    )

    if request.name is not None:
        server.name = request.name
    if request.url is not None:
        server.url = request.url
    if request.transport_type is not None:
        server.transport_type = MCPTransportType(request.transport_type)
    if request.headers is not None:
        server.headers = request.headers
    if request.is_active is not None:
        server.is_active = request.is_active
    if request.description is not None:
        server.description = request.description

    if triggers_override:
        ctx = get_context()
        if ctx is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        user_id = ctx.user.user_id.strip()
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        server = mark_server_override_locked(server=server, user_id=user_id)

    _ = await container.mcp_server_repository.set(server)
    logger.info(f"MCP server updated: {server_id}")
    return await _server_response(container, server)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    container: ContainerDep,
) -> dict[str, str]:
    """Удаляет MCP сервер."""
    await _require_company_member(container)
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Удаляем связанные tools
    for tool_id in server.cached_tools:
        require_not_builtin_tool_id(tool_id, source="mcp cached_tools")
        _ = await container.tool_repository.delete(tool_id)
        await container.flow_access_service.sync_tool_deleted(
            tool_id, company_id=require_active_company().company_id
        )

    _ = await container.mcp_server_repository.delete(server_id)
    logger.info(f"MCP server deleted: {server_id}")
    return {"status": "deleted", "server_id": server_id}


@router.post("/servers/{server_id}/sync", response_model=MCPSyncResponse)
async def sync_server_tools(
    server_id: str,
    container: ContainerDep,
) -> MCPSyncResponse:
    """
    Синхронизирует tools с MCP сервера.

    Та же логика, что и при авто-синхронизации (`apps.flows.src.services.mcp_sync`).
    """
    await _require_company_member(container)
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        _tool_ids, tools = await sync_mcp_server_tools(
            container=as_flow_runtime_container(container),
            server_config=server,
        )
    except MCPClientError as e:
        raise HTTPException(status_code=502, detail=f"MCP server error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}") from e

    logger.info("MCP server %s: synced %s tools", server_id, len(tools))

    return MCPSyncResponse(
        success=True,
        tools_count=len(tools),
        tools=[
            MCPToolResponse(
                name=t.tool_name,
                title=t.title,
                description=t.description,
                parameters_schema=t.parameters_schema,
                output_schema=t.output_schema,
                schema_hash=t.schema_hash,
                schema_version=t.schema_version,
            )
            for t in tools
        ],
    )


@router.post("/servers/{server_id}/test", response_model=MCPTestResponse)
async def test_server_connection(
    server_id: str,
    container: ContainerDep,
) -> MCPTestResponse:
    """Тестирует подключение к MCP серверу."""
    await _require_company_member(container)
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    runtime = as_flow_runtime_container(container)
    try:
        variables = await resolve_mcp_client_variables(runtime, server)
    except MCPClientError as exc:
        raise HTTPException(status_code=502, detail=f"MCP server error: {exc}") from exc

    client = MCPClient(server, variables)

    try:
        _ = await client.initialize()
        tools = await client.list_tools()
    except MCPClientError as e:
        raise HTTPException(status_code=502, detail=f"MCP server error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}")

    return MCPTestResponse(
        success=True,
        message="Connection successful",
        tools_count=len(tools),
        transport_type=server.transport_type.value,
        url=server.url,
    )


@router.post("/servers/{server_id}/reset_catalog_defaults", response_model=MCPServerResponse)
async def reset_catalog_defaults(
    server_id: str,
    container: ContainerDep,
) -> MCPServerResponse:
    """Сбрасывает catalog-managed MCP сервер к snapshot из глобального catalog."""
    await _require_company_member(container)
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.source != MCPServerSource.CATALOG:
        raise HTTPException(status_code=400, detail="reset_catalog_defaults requires source=catalog")
    if server.catalog_id is None:
        raise HTTPException(status_code=400, detail="catalog_id is required for reset")

    entry = await container.mcp_catalog_repository.get(server.catalog_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Catalog entry not found")

    try:
        reset_server = apply_catalog_entry_to_server(server=server, entry=entry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _ = await container.mcp_server_repository.set(reset_server)
    try:
        _ = await sync_mcp_server_tools(
            container=as_flow_runtime_container(container),
            server_config=reset_server,
        )
    except MCPClientError as exc:
        raise HTTPException(status_code=502, detail=f"MCP server error: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Connection error: {exc}") from exc

    stored = await container.mcp_server_repository.get(server_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Server not found after reset")
    logger.info("MCP server reset from catalog: server_id=%s catalog_id=%s", server_id, entry.catalog_id)
    return await _server_response(container, stored)


@router.get("/branding", response_model=OffsetPage[MCPServerBrandingResponse])
async def list_mcp_branding(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPServerBrandingResponse]:
    """Глобальные иконки MCP по slug."""
    items, total = await container.mcp_branding_service.list_branding(
        search=search,
        limit=limit,
        offset=offset,
    )
    return OffsetPage[MCPServerBrandingResponse](
        items=[_branding_resolved_to_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/branding/slug-suggest", response_model=MCPServerBrandingSlugSuggestResponse)
async def suggest_mcp_branding_slugs(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> MCPServerBrandingSlugSuggestResponse:
    slugs = await container.mcp_branding_service.suggest_branding_slugs(search=search, limit=limit)
    return MCPServerBrandingSlugSuggestResponse(slugs=slugs)


@router.put("/branding/{server_id}", response_model=MCPServerBrandingResponse)
async def upsert_mcp_branding(
    server_id: str,
    request: MCPServerBrandingUpsertRequest,
    container: ContainerDep,
) -> MCPServerBrandingResponse:
    """Задаёт иконку MCP сервера по slug (только system company)."""
    resolved = await container.mcp_branding_service.upsert_branding(
        server_id,
        request.icon_file_id,
    )
    return _branding_resolved_to_response(resolved)


@router.delete("/branding/{server_id}", status_code=204)
async def delete_mcp_branding(server_id: str, container: ContainerDep) -> None:
    """Удаляет иконку MCP сервера по slug (только system company)."""
    await container.mcp_branding_service.delete_branding(server_id)
