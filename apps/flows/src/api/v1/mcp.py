"""REST-зеркало MCP: servers, branding и catalog Store — один `op_*` на verb."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.mcp_operations import (
    op_flows_mcp_branding_list,
    op_flows_mcp_branding_remove,
    op_flows_mcp_branding_slug_suggest,
    op_flows_mcp_branding_upsert,
    op_flows_mcp_catalog_install,
    op_flows_mcp_catalog_list,
    op_flows_mcp_catalog_uninstall,
    op_flows_mcp_servers_create,
    op_flows_mcp_servers_item,
    op_flows_mcp_servers_list,
    op_flows_mcp_servers_remove,
    op_flows_mcp_servers_reset_catalog_defaults,
    op_flows_mcp_servers_sync,
    op_flows_mcp_servers_test,
    op_flows_mcp_servers_update,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.mcp import (
    MCPServerConfig,
    MCPServerDeletedResponse,
    MCPServerIdPayload,
    MCPServerListPayload,
    MCPServerUpdatePayload,
    MCPServerUpdateRequest,
    MCPSyncResponse,
    MCPTestResponse,
)
from apps.flows.src.models.mcp_branding import (
    MCPServerBrandingDeletedResponse,
    MCPServerBrandingIdPayload,
    MCPServerBrandingListPayload,
    MCPServerBrandingResolved,
    MCPServerBrandingSlugSuggestPayload,
    MCPServerBrandingSlugSuggestResponse,
    MCPServerBrandingUpsertPayload,
    MCPServerBrandingUpsertRequest,
)
from apps.flows.src.models.mcp_catalog import (
    MCPCatalogIdPayload,
    MCPCatalogListPayload,
    MCPCatalogStoreItem,
    MCPCatalogUninstalledResponse,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(tags=["mcp"])


@router.get("/servers", response_model=OffsetPage[MCPServerConfig])
async def list_servers(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPServerConfig]:
    return await op_flows_mcp_servers_list(
        MCPServerListPayload(search=search, limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("/servers", response_model=MCPServerConfig)
async def create_server(
    payload: MCPServerConfig,
    container: ContainerDep,
) -> MCPServerConfig:
    return await op_flows_mcp_servers_create(
        payload,
        user=require_context().user,
        container=container,
    )


@router.get("/servers/{server_id}", response_model=MCPServerConfig)
async def get_server(
    server_id: str,
    container: ContainerDep,
) -> MCPServerConfig:
    return await op_flows_mcp_servers_item(
        MCPServerIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )


@router.put("/servers/{server_id}", response_model=MCPServerConfig)
async def update_server(
    server_id: str,
    body: MCPServerUpdateRequest,
    container: ContainerDep,
) -> MCPServerConfig:
    return await op_flows_mcp_servers_update(
        MCPServerUpdatePayload.model_validate(
            {"server_id": server_id, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/servers/{server_id}", response_model=MCPServerDeletedResponse)
async def delete_server(
    server_id: str,
    container: ContainerDep,
) -> MCPServerDeletedResponse:
    return await op_flows_mcp_servers_remove(
        MCPServerIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )


@router.post("/servers/{server_id}/sync", response_model=MCPSyncResponse)
async def sync_server_tools(
    server_id: str,
    container: ContainerDep,
) -> MCPSyncResponse:
    return await op_flows_mcp_servers_sync(
        MCPServerIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )


@router.post("/servers/{server_id}/test", response_model=MCPTestResponse)
async def test_server_connection(
    server_id: str,
    container: ContainerDep,
) -> MCPTestResponse:
    return await op_flows_mcp_servers_test(
        MCPServerIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )


@router.post("/servers/{server_id}/reset_catalog_defaults", response_model=MCPServerConfig)
async def reset_catalog_defaults(
    server_id: str,
    container: ContainerDep,
) -> MCPServerConfig:
    return await op_flows_mcp_servers_reset_catalog_defaults(
        MCPServerIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )


@router.get("/catalog", response_model=OffsetPage[MCPCatalogStoreItem])
async def list_mcp_catalog(
    container: ContainerDep,
    tier: Annotated[str, Query()] = "store",
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPCatalogStoreItem]:
    return await op_flows_mcp_catalog_list(
        MCPCatalogListPayload(search=search, limit=limit, offset=offset, tier=tier),
        user=require_context().user,
        container=container,
    )


@router.post("/catalog/{catalog_id}/install", response_model=MCPServerConfig)
async def install_mcp_catalog_entry(
    catalog_id: str,
    container: ContainerDep,
) -> MCPServerConfig:
    return await op_flows_mcp_catalog_install(
        MCPCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.delete("/catalog/{catalog_id}/install", response_model=MCPCatalogUninstalledResponse)
async def uninstall_mcp_catalog_entry(
    catalog_id: str,
    container: ContainerDep,
) -> MCPCatalogUninstalledResponse:
    return await op_flows_mcp_catalog_uninstall(
        MCPCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.get("/branding", response_model=OffsetPage[MCPServerBrandingResolved])
async def list_mcp_branding(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[MCPServerBrandingResolved]:
    return await op_flows_mcp_branding_list(
        MCPServerBrandingListPayload(search=search, limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.get("/branding/slug-suggest", response_model=MCPServerBrandingSlugSuggestResponse)
async def suggest_mcp_branding_slugs(
    container: ContainerDep,
    search: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> MCPServerBrandingSlugSuggestResponse:
    return await op_flows_mcp_branding_slug_suggest(
        MCPServerBrandingSlugSuggestPayload(search=search, limit=limit),
        user=require_context().user,
        container=container,
    )


@router.put("/branding/{server_id}", response_model=MCPServerBrandingResolved)
async def upsert_mcp_branding(
    server_id: str,
    body: MCPServerBrandingUpsertRequest,
    container: ContainerDep,
) -> MCPServerBrandingResolved:
    return await op_flows_mcp_branding_upsert(
        MCPServerBrandingUpsertPayload.model_validate(
            {"server_id": server_id, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/branding/{server_id}", response_model=MCPServerBrandingDeletedResponse)
async def delete_mcp_branding(
    server_id: str,
    container: ContainerDep,
) -> MCPServerBrandingDeletedResponse:
    return await op_flows_mcp_branding_remove(
        MCPServerBrandingIdPayload(server_id=server_id),
        user=require_context().user,
        container=container,
    )
