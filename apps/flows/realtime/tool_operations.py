"""Каталог tools: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from apps.flows.realtime.operations import (
    company_scope,
    require_company_member,
    require_view_tool,
    require_view_tool_or_flow,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models import FlowConfig, ToolReference, flow_tool_parameters_schema
from apps.flows.src.models.enums import CodeMode, ReactToolRole
from apps.flows.src.models.flow_config import FlowToolPickerItem
from apps.flows.src.models.tool_contracts import ToolDefinition
from apps.flows.src.models.tool_reference import (
    PickerCategory,
    ToolCreateRequest,
    ToolDeletedResponse,
    ToolIndexMcpFilter,
    ToolListIndexItem,
    ToolResponse,
    ToolsListAllPayload,
    ToolsListPayload,
    ToolsTagGroupsPayload,
    ToolsToolIdPayload,
)
from apps.flows.src.models.tool_tag_group import ToolTagGroup
from apps.flows.src.services.agent_toolkit_service import (
    get_toolkit_ids_for_flow,
    get_toolkit_ids_for_tool,
    set_tool_toolkit_membership,
)
from apps.flows.src.services.tool_definition_builder import build_tool_definition_from_base_tool
from apps.flows.src.services.tool_preview import (
    ToolPreviewRequest,
    ToolPreviewResponse,
    build_tool_preview,
)
from apps.flows.src.tools.base import BaseTool
from apps.flows.tools.builtin_specs import builtin_tool_ids
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.types import JsonObject
from core.websocket import (
    raise_conflict,
    raise_invalid,
    raise_not_found,
)


@dataclass(frozen=True, slots=True)
class _PickerRef:
    item_type: Literal["flow", "tool"]
    object_id: str


def _raise_if_platform_builtin(tool_id: str, *, action: str) -> None:
    if tool_id in builtin_tool_ids():
        raise_conflict(ValueError(f"platform builtin {tool_id!r} cannot be {action}"))


async def _toolkit_ids_for_tool(container: FlowContainer, tool_id: str) -> list[str]:
    return await get_toolkit_ids_for_tool(container.agent_toolkit_repository, tool_id)


async def _toolkit_ids_for_flow(container: FlowContainer, flow_id: str) -> list[str]:
    return await get_toolkit_ids_for_flow(container.agent_toolkit_repository, flow_id)


def _tool_response_from_reference(t: ToolReference, *, agent_toolkit_ids: list[str]) -> ToolResponse:
    return ToolResponse(
        tool_id=t.tool_id,
        title=t.title,
        description=t.description,
        code=t.code,
        language=t.language,
        entrypoint=t.entrypoint,
        parameters_schema=t.parameters_schema,
        tags=t.tags,
        permission=t.permission,
        item_type="tool",
        react_role=t.react_role.value,
        code_mode=t.code_mode.value,
        mcp_server_id=t.mcp_server_id,
        mcp_tool_name=t.mcp_tool_name,
        mcp_schema_hash=t.mcp_schema_hash,
        mcp_schema_version=t.mcp_schema_version,
        mcp_output_schema=t.mcp_output_schema,
        agent_toolkit_ids=agent_toolkit_ids,
    )


def _resolve_registry_tool(container: FlowContainer, tool_id: str) -> BaseTool | None:
    registry = container.tool_registry
    registry.register_builtin_tools()
    return registry.get(tool_id)


async def _require_runnable_tool(container: FlowContainer, tool_id: str) -> BaseTool:
    registry_tool = _resolve_registry_tool(container, tool_id)
    if registry_tool is not None:
        return registry_tool
    stored = await container.tool_repository.get(tool_id)
    if stored is None:
        raise_not_found(LookupError(f"Tool '{tool_id}' not found"))
    try:
        return await container.tool_registry.materialize(stored)
    except ValueError as exc:
        raise_invalid(exc)


def _enrich_tool_response_from_registry(
    container: FlowContainer,
    response: ToolResponse,
) -> ToolResponse:
    registry_tool = _resolve_registry_tool(container, response.tool_id)
    if registry_tool is None:
        return response
    return response.model_copy(
        update={
            "builtin": True,
            "effects": list(registry_tool.effects),
            "confirmation_floor": registry_tool.confirmation_floor,
            "output_schema": registry_tool.output_schema
            if response.output_schema is None
            else response.output_schema,
            "parameters_schema": registry_tool.parameters
            if response.parameters_schema is None
            else response.parameters_schema,
        }
    )


def _tool_response_from_registry_tool(tool: BaseTool) -> ToolResponse:
    return ToolResponse(
        tool_id=tool.name,
        title=tool.name,
        description=tool.description,
        code=None,
        language="python",
        entrypoint=None,
        parameters_schema=tool.parameters,
        output_schema=tool.output_schema,
        effects=list(tool.effects),
        confirmation_floor=tool.confirmation_floor,
        builtin=True,
        tags=tool.get_tags(),
        permission=tool.permission,
        item_type="tool",
        react_role=tool.react_role.value,
        code_mode=None,
        mcp_server_id=None,
        mcp_tool_name=None,
    )


def _flow_response(flow_row: FlowConfig | FlowToolPickerItem) -> ToolResponse:
    return ToolResponse(
        tool_id=flow_row.flow_id,
        title=flow_row.name,
        description=flow_row.description,
        parameters_schema=flow_tool_parameters_schema(),
        tags=flow_row.tags if len(flow_row.tags) > 0 else ["flow"],
        permission=None,
        item_type="flow",
    )


def _index_row_is_mcp(row: ToolListIndexItem) -> bool:
    if row.code_mode == CodeMode.MCP_TOOL:
        return True
    raw_server_id = row.mcp_server_id
    if raw_server_id is not None and raw_server_id.strip():
        return True
    return row.tool_id.startswith("mcp:")


def _picker_text_match(
    *,
    tool_id: str,
    title: str | None,
    description: str | None,
    needle: str | None,
) -> bool:
    if needle is None:
        return True
    hay = " ".join(part for part in (tool_id, title or "", description or "")).lower()
    return needle in hay


def _registry_listed_tools(container: FlowContainer) -> list[BaseTool]:
    registry = container.tool_registry
    registry.register_builtin_tools()
    return [
        tool
        for _, tool in sorted(registry.list_all().items(), key=lambda item: item[0])
        if tool.listed_in_platform_tool_docs
    ]


async def _company_tool_picker_index(
    container: FlowContainer,
    *,
    mcp: ToolIndexMcpFilter,
) -> list[ToolListIndexItem]:
    return await container.tool_repository.list_index(
        mcp=mcp,
        exclude_tool_ids=builtin_tool_ids(),
    )


async def _flow_picker_refs(
    container: FlowContainer,
    *,
    needle: str | None,
) -> list[_PickerRef]:
    refs: list[_PickerRef] = []
    for row in await container.flow_repository.list_picker_index():
        if not _picker_text_match(
            tool_id=row.flow_id,
            title=row.name,
            description=row.description,
            needle=needle,
        ):
            continue
        refs.append(_PickerRef(item_type="flow", object_id=row.flow_id))
    return refs


def _tool_picker_mcp_filter(*, include_mcp: bool, mcp_only: bool) -> ToolIndexMcpFilter:
    if mcp_only:
        return "only"
    if not include_mcp:
        return "exclude"
    return "all"


async def _tool_picker_refs(
    container: FlowContainer,
    *,
    include_mcp: bool,
    mcp_only: bool,
    needle: str | None,
) -> list[_PickerRef]:
    refs: list[_PickerRef] = []
    mcp_filter = _tool_picker_mcp_filter(include_mcp=include_mcp, mcp_only=mcp_only)
    for row in await _company_tool_picker_index(container, mcp=mcp_filter):
        is_mcp = _index_row_is_mcp(row)
        if mcp_only and not is_mcp:
            continue
        if not include_mcp and is_mcp:
            continue
        if not _picker_text_match(
            tool_id=row.tool_id,
            title=row.title,
            description=row.description,
            needle=needle,
        ):
            continue
        refs.append(_PickerRef(item_type="tool", object_id=row.tool_id))
    if mcp_only:
        return refs
    for tool in _registry_listed_tools(container):
        if not _picker_text_match(
            tool_id=tool.name,
            title=tool.name,
            description=tool.description,
            needle=needle,
        ):
            continue
        refs.append(_PickerRef(item_type="tool", object_id=tool.name))
    return refs


async def _page_viewable_picker_refs(
    container: FlowContainer,
    catalog: list[_PickerRef],
    *,
    limit: int,
    offset: int,
) -> list[_PickerRef]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if not catalog or limit <= 0:
        return []
    needed = offset + limit
    viewable: list[_PickerRef] = []
    pos = 0
    scope = company_scope()
    while pos < len(catalog) and len(viewable) < needed:
        remaining = needed - len(viewable)
        window = catalog[pos : pos + remaining]
        pos += len(window)
        flow_ids = [ref.object_id for ref in window if ref.item_type == "flow"]
        tool_ids = [ref.object_id for ref in window if ref.item_type == "tool"]
        allowed_flows: set[str] = set()
        if flow_ids:
            allowed_flows = set(
                await container.flow_access_service.filter_viewable_flow_ids(
                    flow_ids, user_id=scope.user_id, company_id=scope.company_id
                )
            )
        allowed_tools: set[str] = set()
        if tool_ids:
            allowed_tools = set(
                await container.flow_access_service.filter_viewable_tool_ids(
                    tool_ids, user_id=scope.user_id, company_id=scope.company_id
                )
            )
        for ref in window:
            if ref.item_type == "flow" and ref.object_id in allowed_flows:
                viewable.append(ref)
            elif ref.item_type == "tool" and ref.object_id in allowed_tools:
                viewable.append(ref)
    return viewable[offset : offset + limit]


async def _hydrate_picker_page(
    container: FlowContainer,
    page_refs: list[_PickerRef],
) -> list[ToolResponse]:
    flow_ids = [ref.object_id for ref in page_refs if ref.item_type == "flow"]
    tool_ids = [ref.object_id for ref in page_refs if ref.item_type == "tool"]
    platform_ids = builtin_tool_ids()
    company_tool_ids = [tid for tid in tool_ids if tid not in platform_ids]
    flows_by_id = await container.flow_repository.get_many(flow_ids) if flow_ids else {}
    tools_by_id = (
        await container.tool_repository.get_many(company_tool_ids) if company_tool_ids else {}
    )
    items: list[ToolResponse] = []
    for ref in page_refs:
        if ref.item_type == "flow":
            flow_row = flows_by_id.get(ref.object_id)
            if flow_row is None:
                raise RuntimeError(
                    f"flow {ref.object_id!r} passed picker Check but is missing from flow_repository"
                )
            items.append(_flow_response(flow_row))
            continue
        if ref.object_id in platform_ids:
            registry_tool = _resolve_registry_tool(container, ref.object_id)
            if registry_tool is None:
                raise RuntimeError(
                    f"platform builtin {ref.object_id!r} is missing from ToolRegistry"
                )
            items.append(_tool_response_from_registry_tool(registry_tool))
            continue
        tool_row = tools_by_id.get(ref.object_id)
        if tool_row is None:
            raise RuntimeError(
                f"tool {ref.object_id!r} passed picker Check but is missing from tool_repository"
            )
        items.append(
            _enrich_tool_response_from_registry(
                container,
                _tool_response_from_reference(tool_row, agent_toolkit_ids=[]),
            )
        )
    return items


async def _tool_picker_total(
    container: FlowContainer,
    *,
    mcp: ToolIndexMcpFilter,
    include_registry: bool,
    needle: str | None,
    catalog: list[_PickerRef],
) -> int:
    if needle is not None:
        return len(catalog)
    total = await container.tool_repository.count_index(
        mcp=mcp,
        exclude_tool_ids=builtin_tool_ids(),
    )
    if include_registry:
        total += len(_registry_listed_tools(container))
    return total


async def _list_picker_tools_and_flows(
    container: FlowContainer,
    *,
    picker_category: PickerCategory,
    limit: int,
    offset: int,
    q: str | None = None,
) -> OffsetPage[ToolResponse]:
    needle = q.strip().lower() if isinstance(q, str) and q.strip() else None
    scope = company_scope()
    if picker_category == PickerCategory.FLOW:
        catalog = await _flow_picker_refs(container, needle=needle)
        page_ids = await container.flow_access_service.page_viewable_flow_ids(
            [ref.object_id for ref in catalog],
            user_id=scope.user_id,
            company_id=scope.company_id,
            offset=offset,
            limit=limit,
        )
        page_refs = [_PickerRef(item_type="flow", object_id=flow_id) for flow_id in page_ids]
        total = len(catalog)
    elif picker_category == PickerCategory.MCP:
        catalog = await _tool_picker_refs(
            container, include_mcp=True, mcp_only=True, needle=needle
        )
        page_ids = await container.flow_access_service.page_viewable_tool_ids(
            [ref.object_id for ref in catalog],
            user_id=scope.user_id,
            company_id=scope.company_id,
            offset=offset,
            limit=limit,
        )
        page_refs = [_PickerRef(item_type="tool", object_id=tool_id) for tool_id in page_ids]
        total = await _tool_picker_total(
            container,
            mcp="only",
            include_registry=False,
            needle=needle,
            catalog=catalog,
        )
    elif picker_category == PickerCategory.CODE:
        catalog = await _tool_picker_refs(
            container, include_mcp=False, mcp_only=False, needle=needle
        )
        page_ids = await container.flow_access_service.page_viewable_tool_ids(
            [ref.object_id for ref in catalog],
            user_id=scope.user_id,
            company_id=scope.company_id,
            offset=offset,
            limit=limit,
        )
        page_refs = [_PickerRef(item_type="tool", object_id=tool_id) for tool_id in page_ids]
        total = await _tool_picker_total(
            container,
            mcp="exclude",
            include_registry=True,
            needle=needle,
            catalog=catalog,
        )
    else:
        catalog = [
            *(await _flow_picker_refs(container, needle=needle)),
            *(await _tool_picker_refs(
                container, include_mcp=True, mcp_only=False, needle=needle
            )),
        ]
        page_refs = await _page_viewable_picker_refs(
            container, catalog, limit=limit, offset=offset
        )
        if needle is not None:
            total = len(catalog)
        else:
            flow_total = len([ref for ref in catalog if ref.item_type == "flow"])
            tool_total = await _tool_picker_total(
                container,
                mcp="all",
                include_registry=True,
                needle=None,
                catalog=[],
            )
            total = flow_total + tool_total
    return OffsetPage[ToolResponse](
        items=await _hydrate_picker_page(container, page_refs),
        total=total,
        limit=limit,
        offset=offset,
    )


async def op_flows_tools_list(
    payload: ToolsListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[ToolResponse]:
    _ = user
    scope = await require_company_member(container)
    tools, total = await asyncio.gather(
        container.tool_repository.list(limit=payload.limit, offset=payload.offset),
        container.tool_repository.count_all(),
    )
    allowed_ids = set(
        await container.flow_access_service.filter_viewable_tool_ids(
            [tool_row.tool_id for tool_row in tools],
            user_id=scope.user_id,
            company_id=scope.company_id,
        )
    )
    tools = [tool_row for tool_row in tools if tool_row.tool_id in allowed_ids]
    response_items: list[ToolResponse] = []
    for tool_row in tools:
        toolkit_ids = await _toolkit_ids_for_tool(container, tool_row.tool_id)
        response_items.append(
            _enrich_tool_response_from_registry(
                container,
                _tool_response_from_reference(tool_row, agent_toolkit_ids=toolkit_ids),
            )
        )
    return OffsetPage[ToolResponse](
        items=response_items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_tools_list_all(
    payload: ToolsListAllPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[ToolResponse]:
    _ = user
    _ = await require_company_member(container)
    return await _list_picker_tools_and_flows(
        container,
        picker_category=payload.picker_category
        if payload.picker_category is not None
        else PickerCategory.ALL,
        limit=payload.limit,
        offset=payload.offset,
        q=payload.q,
    )


async def op_flows_tools_tag_groups(
    payload: ToolsTagGroupsPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[ToolTagGroup]:
    _ = user
    _ = await require_company_member(container)
    groups = await container.tool_tag_group_service.list_groups(
        limit=payload.limit, offset=payload.offset
    )
    items = list(groups)
    page_len = len(items)
    total = payload.offset + page_len if page_len < payload.limit else payload.offset + page_len + 1
    return OffsetPage[ToolTagGroup](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_tools_preview(
    payload: ToolPreviewRequest,
    *,
    user: User,
    container: FlowContainer,
) -> ToolPreviewResponse:
    _ = user
    _ = await require_view_tool(container, payload.tool_id)
    tool = await _require_runnable_tool(container, payload.tool_id)
    return build_tool_preview(
        tool,
        binding_overrides=payload.binding_overrides,
        model_args=payload.model_args,
    )


async def op_flows_tools_contract(
    payload: ToolsToolIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ToolDefinition:
    _ = user
    _ = await require_view_tool(container, payload.tool_id)
    tool = await _require_runnable_tool(container, payload.tool_id)
    return build_tool_definition_from_base_tool(tool)


async def op_flows_tools_item(
    payload: ToolsToolIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ToolResponse:
    _ = user
    _ = await require_view_tool_or_flow(container, payload.tool_id)
    tool = await container.tool_repository.get(payload.tool_id)
    if tool is not None:
        toolkit_ids = await _toolkit_ids_for_tool(container, tool.tool_id)
        return _enrich_tool_response_from_registry(
            container,
            _tool_response_from_reference(tool, agent_toolkit_ids=toolkit_ids),
        )
    registry_tool = _resolve_registry_tool(container, payload.tool_id)
    if registry_tool is not None:
        return _tool_response_from_registry_tool(registry_tool)
    flow_cfg = await container.flow_repository.get(payload.tool_id)
    if flow_cfg is None:
        raise_not_found(LookupError("Tool not found"))
    flow_toolkit_ids = await _toolkit_ids_for_flow(container, flow_cfg.flow_id)
    flow_item = _flow_response(flow_cfg)
    return flow_item.model_copy(update={"agent_toolkit_ids": flow_toolkit_ids})


async def op_flows_tools_create(
    payload: ToolCreateRequest,
    *,
    user: User,
    container: FlowContainer,
) -> ToolResponse:
    _ = user
    _raise_if_platform_builtin(payload.tool_id, action="created")
    scope = await require_company_member(container)
    react_role = (
        ReactToolRole(payload.react_role) if payload.react_role is not None else ReactToolRole.STANDARD
    )
    ps: JsonObject = payload.parameters_schema
    raw_properties = ps.get("properties")
    if ps.get("type") != "object" or not isinstance(raw_properties, dict):
        raise_invalid(
            ValueError(
                "parameters_schema must be JSON Schema object with type: object and properties"
            )
        )
    entrypoint = payload.entrypoint
    if entrypoint is not None:
        stripped = entrypoint.strip()
        entrypoint = stripped if stripped else None
    ref = ToolReference(
        tool_id=payload.tool_id,
        title=payload.title,
        description=payload.description,
        code=payload.code,
        language=payload.language,
        entrypoint=entrypoint,
        parameters_schema=ps,
        tags=payload.tags,
        react_role=react_role,
    )
    _ = await container.tool_repository.set(ref)
    await container.flow_access_service.sync_tool_saved(
        ref.tool_id,
        company_id=scope.company_id,
        permission=ref.permission,
    )
    await set_tool_toolkit_membership(
        container.agent_toolkit_repository,
        tool_id=ref.tool_id,
        toolkit_ids=list(payload.agent_toolkit_ids),
    )
    return _enrich_tool_response_from_registry(
        container,
        _tool_response_from_reference(
            ref,
            agent_toolkit_ids=list(payload.agent_toolkit_ids),
        ),
    )


async def op_flows_tools_remove(
    payload: ToolsToolIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ToolDeletedResponse:
    _ = user
    _raise_if_platform_builtin(payload.tool_id, action="deleted")
    scope = await require_view_tool(container, payload.tool_id)
    deleted = await container.tool_repository.delete(payload.tool_id)
    if not deleted:
        raise_not_found(LookupError("Tool not found"))
    await container.flow_access_service.sync_tool_deleted(
        payload.tool_id, company_id=scope.company_id
    )
    return ToolDeletedResponse(status="deleted", tool_id=payload.tool_id)
