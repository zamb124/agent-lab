"""Каталог MCP серверов: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.models.mcp import (
    MCPServerConfig,
    MCPServerDeletedResponse,
    MCPServerIdPayload,
    MCPServerListPayload,
    MCPServerSource,
    MCPServerUpdatePayload,
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
)
from apps.flows.src.models.mcp_catalog import (
    MCPCatalogIdPayload,
    MCPCatalogListPayload,
    MCPCatalogStoreItem,
    MCPCatalogUninstalledResponse,
)
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
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import (
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
    raise_upstream,
)


async def attach_mcp_server_icon(
    container: FlowContainer,
    server: MCPServerConfig,
    *,
    icon_url_map: dict[str, str] | None = None,
) -> MCPServerConfig:
    try:
        if icon_url_map is None:
            icon_url = await container.mcp_branding_service.get_icon_url(server.server_id)
        else:
            icon_url = icon_url_map.get(server.server_id)
    except ValueError as exc:
        raise_invalid(exc)
    return server.model_copy(update={"icon_url": icon_url})


async def persist_mcp_server(container: FlowContainer, server: MCPServerConfig) -> None:
    _ = await container.mcp_server_repository.set(
        server.model_copy(update={"icon_url": None})
    )


async def _require_server(
    container: FlowContainer, server_id: str
) -> MCPServerConfig:
    server = await container.mcp_server_repository.get(server_id)
    if server is None:
        raise_not_found(LookupError("Server not found"))
    return server


async def op_flows_mcp_servers_list(
    payload: MCPServerListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[MCPServerConfig]:
    _ = user
    _ = await require_company_member(container)
    servers = await container.mcp_server_repository.list(limit=5000, offset=0)
    filtered_servers = filter_mcp_servers_by_search(servers, payload.search)
    ordered_servers = sort_mcp_servers_for_display(filtered_servers)
    total = len(ordered_servers)
    page_servers = ordered_servers[payload.offset : payload.offset + payload.limit]
    try:
        icon_url_map = await container.mcp_branding_service.build_icon_url_map_for_server_ids(
            [server.server_id for server in page_servers]
        )
    except ValueError as exc:
        raise_invalid(exc)
    items = [
        await attach_mcp_server_icon(container, server, icon_url_map=icon_url_map)
        for server in page_servers
    ]
    return OffsetPage[MCPServerConfig](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_mcp_servers_item(
    payload: MCPServerIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerConfig:
    _ = user
    _ = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    return await attach_mcp_server_icon(container, server)


async def op_flows_mcp_servers_create(
    payload: MCPServerConfig,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerConfig:
    _ = user
    _ = await require_company_member(container)
    existing = await container.mcp_server_repository.get(payload.server_id)
    if existing is not None:
        raise_conflict(ValueError(f"Server {payload.server_id} already exists"))
    server = MCPServerConfig(
        server_id=payload.server_id,
        name=payload.name,
        url=payload.url,
        transport_type=payload.transport_type,
        headers=payload.headers,
        description=payload.description,
        source=MCPServerSource.MANUAL,
    )
    await persist_mcp_server(container, server)
    return await attach_mcp_server_icon(container, server)


async def op_flows_mcp_servers_update(
    payload: MCPServerUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerConfig:
    _ = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    triggers_override = mcp_server_update_triggers_override(
        server=server,
        name=payload.name,
        url=payload.url,
        transport_type=payload.transport_type,
        headers=payload.headers,
        description=payload.description,
        is_active=payload.is_active,
    )
    if payload.name is not None:
        server.name = payload.name
    if payload.url is not None:
        server.url = payload.url
    if payload.transport_type is not None:
        server.transport_type = payload.transport_type
    if payload.headers is not None:
        server.headers = payload.headers
    if payload.is_active is not None:
        server.is_active = payload.is_active
    if payload.description is not None:
        server.description = payload.description
    if triggers_override:
        user_id = user.user_id.strip()
        if not user_id:
            raise_forbidden(ValueError("Authentication required"))
        server = mark_server_override_locked(server=server, user_id=user_id)
    await persist_mcp_server(container, server)
    return await attach_mcp_server_icon(container, server)


async def op_flows_mcp_servers_remove(
    payload: MCPServerIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerDeletedResponse:
    _ = user
    scope = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    for tool_id in server.cached_tools:
        require_not_builtin_tool_id(tool_id, source="mcp cached_tools")
        _ = await container.tool_repository.delete(tool_id)
        await container.flow_access_service.sync_tool_deleted(
            tool_id, company_id=scope.company_id
        )
    _ = await container.mcp_server_repository.delete(payload.server_id)
    return MCPServerDeletedResponse(status="deleted", server_id=payload.server_id)


async def op_flows_mcp_servers_sync(
    payload: MCPServerIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPSyncResponse:
    _ = user
    _ = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    try:
        _tool_ids, tools = await sync_mcp_server_tools(
            container=as_flow_runtime_container(container),
            server_config=server,
        )
    except MCPClientError as exc:
        raise_upstream(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return MCPSyncResponse(success=True, tools_count=len(tools), tools=tools)


async def op_flows_mcp_servers_test(
    payload: MCPServerIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPTestResponse:
    _ = user
    _ = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    runtime = as_flow_runtime_container(container)
    try:
        variables = await resolve_mcp_client_variables(runtime, server)
        client = MCPClient(server, variables)
        _ = await client.initialize()
        tools = await client.list_tools()
    except MCPClientError as exc:
        raise_upstream(exc)
    return MCPTestResponse(
        success=True,
        message="Connection successful",
        tools_count=len(tools),
        transport_type=server.transport_type,
        url=server.url,
    )


async def op_flows_mcp_servers_reset_catalog_defaults(
    payload: MCPServerIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerConfig:
    _ = user
    _ = await require_company_member(container)
    server = await _require_server(container, payload.server_id)
    if server.source != MCPServerSource.CATALOG:
        raise_invalid(ValueError("reset_catalog_defaults requires source=catalog"))
    if server.catalog_id is None:
        raise_invalid(ValueError("catalog_id is required for reset"))
    entry = await container.mcp_catalog_repository.get(server.catalog_id)
    if entry is None:
        raise_not_found(LookupError("Catalog entry not found"))
    try:
        reset_server = apply_catalog_entry_to_server(server=server, entry=entry)
    except ValueError as exc:
        raise_invalid(exc)
    await persist_mcp_server(container, reset_server)
    try:
        _ = await sync_mcp_server_tools(
            container=as_flow_runtime_container(container),
            server_config=reset_server,
        )
    except MCPClientError as exc:
        raise_upstream(exc)
    except ValueError as exc:
        raise_invalid(exc)
    stored = await container.mcp_server_repository.get(payload.server_id)
    if stored is None:
        raise_not_found(LookupError("Server not found after reset"))
    return await attach_mcp_server_icon(container, stored)


async def op_flows_mcp_branding_list(
    payload: MCPServerBrandingListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[MCPServerBrandingResolved]:
    _ = user
    _ = await require_company_member(container)
    try:
        items, total = await container.mcp_branding_service.list_branding(
            search=payload.search,
            limit=payload.limit,
            offset=payload.offset,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return OffsetPage[MCPServerBrandingResolved](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_mcp_branding_slug_suggest(
    payload: MCPServerBrandingSlugSuggestPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerBrandingSlugSuggestResponse:
    _ = user
    _ = await require_company_member(container)
    slugs = await container.mcp_branding_service.suggest_branding_slugs(
        search=payload.search,
        limit=payload.limit,
    )
    return MCPServerBrandingSlugSuggestResponse(slugs=slugs)


async def op_flows_mcp_branding_upsert(
    payload: MCPServerBrandingUpsertPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerBrandingResolved:
    _ = user
    _ = await require_company_member(container)
    try:
        return await container.mcp_branding_service.upsert_branding(
            payload.server_id,
            payload.icon_file_id,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_mcp_branding_remove(
    payload: MCPServerBrandingIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerBrandingDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    try:
        await container.mcp_branding_service.delete_branding(payload.server_id)
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)
    except LookupError as exc:
        raise_not_found(exc)
    return MCPServerBrandingDeletedResponse(status="deleted", server_id=payload.server_id)


async def op_flows_mcp_catalog_list(
    payload: MCPCatalogListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[MCPCatalogStoreItem]:
    _ = user
    _ = await require_company_member(container)
    if payload.tier != "store":
        raise_invalid(ValueError("Only tier=store is supported"))
    runtime = as_flow_runtime_container(container)
    page_entries, total = await list_store_catalog_entries(
        container=runtime,
        search=payload.search,
        limit=payload.limit,
        offset=payload.offset,
    )
    try:
        icon_url_map = await container.mcp_branding_service.build_icon_url_map_for_server_ids(
            [
                server_id_from_catalog_id(entry.catalog_id)
                for entry, _installed, _platform_curated in page_entries
            ]
        )
    except ValueError as exc:
        raise_invalid(exc)
    items = [
        MCPCatalogStoreItem(
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
    return OffsetPage[MCPCatalogStoreItem](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_mcp_catalog_install(
    payload: MCPCatalogIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPServerConfig:
    _ = user
    _ = await require_company_member(container)
    runtime = as_flow_runtime_container(container)
    try:
        server = await install_catalog_entry_for_company(
            container=runtime,
            catalog_id=payload.catalog_id,
        )
    except ValueError as exc:
        raise_invalid(exc)
    except MCPClientError as exc:
        raise_upstream(exc)
    return await attach_mcp_server_icon(container, server)


async def op_flows_mcp_catalog_uninstall(
    payload: MCPCatalogIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> MCPCatalogUninstalledResponse:
    _ = user
    _ = await require_company_member(container)
    runtime = as_flow_runtime_container(container)
    try:
        await uninstall_catalog_entry_from_company(
            container=runtime,
            catalog_id=payload.catalog_id,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return MCPCatalogUninstalledResponse(status="uninstalled", catalog_id=payload.catalog_id)
