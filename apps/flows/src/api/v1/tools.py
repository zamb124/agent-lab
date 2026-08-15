"""
API endpoints для tools.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig, ToolReference, flow_tool_parameters_schema
from apps.flows.src.models.enums import CodeMode, ReactToolRole
from apps.flows.src.models.flow_config import FlowToolPickerItem
from apps.flows.src.models.tool_contracts import ToolDefinition
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
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.types import AuthzRelation
from core.context import require_context
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.types import JsonObject

logger = get_logger(__name__)


def _actor_user_id() -> str:
    return require_context().user.user_id


async def _require_company_member(container: ContainerDep) -> None:
    ctx = require_context()
    if ctx.active_company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    await container.authz_service.require_can_view(
        AuthzObject.company(ctx.active_company.company_id),
        user_id=ctx.user.user_id,
    )


async def _require_view_tool(container: ContainerDep, tool_id: str) -> None:
    await container.authz_service.require_can_view(
        AuthzObject.tool(tool_id), user_id=_actor_user_id()
    )


async def _require_view_tool_or_flow(container: ContainerDep, object_id: str) -> None:
    """GET /tools/{id} может быть tool или flow-as-tool; Check обоих до existence."""
    user_id = _actor_user_id()
    allowed = await container.authz_service.batch_check(
        [
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.tool(object_id),
                correlation_id="tool",
            ),
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.flow(object_id),
                correlation_id="flow",
            ),
        ]
    )
    if not any(allowed):
        raise AuthzDenied(f"denied user:{user_id} can_view tool|flow:{object_id}")


async def _filter_picker_items(
    container: ContainerDep, items: list[ToolResponse]
) -> list[ToolResponse]:
    user_id = _actor_user_id()
    allowed_flows = set(
        await container.flow_access_service.list_viewable_flow_ids(user_id=user_id)
    )
    allowed_tools = set(
        await container.flow_access_service.list_viewable_tool_ids(user_id=user_id)
    )
    return [
        item
        for item in items
        if (
            item.item_type == "flow"
            and item.tool_id in allowed_flows
        )
        or (item.item_type != "flow" and item.tool_id in allowed_tools)
    ]

router = APIRouter(tags=["tools"])


class ToolCreateRequest(StrictBaseModel):
    """Запрос на создание tool"""

    tool_id: str
    title: str | None = None
    description: str | None = None
    code: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    parameters_schema: JsonObject
    tags: list[str] | None = None
    react_role: str | None = None
    agent_toolkit_ids: list[str] = Field(default_factory=list)


class ToolResponse(StrictBaseModel):
    """Ответ с данными tool"""

    tool_id: str
    title: str | None
    description: str | None
    code: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    parameters_schema: JsonObject | None = None
    output_schema: JsonObject | None = None
    effects: list[str] = Field(default_factory=list)
    confirmation_floor: str | None = None
    builtin: bool = False
    tags: list[str] = Field(default_factory=list)
    permission: str | list[str] | None = None
    item_type: str = "tool"  # tool или flow (запись из репозитория flows)
    react_role: str | None = None
    code_mode: str | None = None  # inline_code или mcp_tool
    mcp_server_id: str | None = None  # ID MCP сервера
    mcp_tool_name: str | None = None  # имя tool на MCP (если id не mcp:…)
    mcp_schema_hash: str | None = None
    mcp_schema_version: str | None = None
    mcp_output_schema: JsonObject | None = None
    agent_toolkit_ids: list[str] = Field(default_factory=list)


_TOOLS_MAX_LIMIT = 2000
_TOOLS_ALL_HTTP_MAX_LIMIT = 20
_TAG_GROUPS_HTTP_MAX_LIMIT = 200


class PickerCategory(str, Enum):
    ALL = "all"
    CODE = "code"
    FLOW = "flow"
    MCP = "mcp"


async def _toolkit_ids_for_tool(container: ContainerDep, tool_id: str) -> list[str]:
    return await get_toolkit_ids_for_tool(container.agent_toolkit_repository, tool_id)


async def _toolkit_ids_for_flow(container: ContainerDep, flow_id: str) -> list[str]:
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
        tags=t.tags or ["misc"],
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


def _enrich_tool_response_from_registry(
    container: ContainerDep,
    response: ToolResponse,
) -> ToolResponse:
    """Attach contract fields when tool_id matches a process builtin."""
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


def _resolve_registry_tool(container: ContainerDep, tool_id: str) -> BaseTool | None:
    registry = container.tool_registry
    registry.register_builtin_tools()
    return registry.get(tool_id)


def _flow_response(flow_row: FlowConfig | FlowToolPickerItem) -> ToolResponse:
    return ToolResponse(
        tool_id=flow_row.flow_id,
        title=flow_row.name,
        description=flow_row.description,
        parameters_schema=flow_tool_parameters_schema(),
        tags=flow_row.tags or ["flow"],
        permission=None,
        item_type="flow",
    )


def _is_mcp_tool_reference(tool_row: ToolReference) -> bool:
    if tool_row.code_mode == CodeMode.MCP_TOOL:
        return True
    raw_server_id = tool_row.mcp_server_id
    if raw_server_id is not None and raw_server_id.strip():
        return True
    return tool_row.tool_id.startswith("mcp:")


def _append_registry_tools(
    container: ContainerDep,
    *,
    seen_tool_ids: set[str],
) -> list[ToolResponse]:
    registry = container.tool_registry
    registry.register_builtin_tools()
    items: list[ToolResponse] = []
    for tool_id, tool in sorted(registry.list_all().items(), key=lambda item: item[0]):
        if tool_id in seen_tool_ids:
            continue
        if not tool.listed_in_platform_tool_docs:
            continue
        items.append(_tool_response_from_registry_tool(tool))
        seen_tool_ids.add(tool_id)
    return items


async def _collect_picker_flow_items(container: ContainerDep) -> list[ToolResponse]:
    flow_ids = await container.flow_access_service.list_viewable_flow_ids(
        user_id=_actor_user_id()
    )
    by_id = await container.flow_repository.get_many(flow_ids)
    return [
        _flow_response(by_id[flow_id])
        for flow_id in flow_ids
        if flow_id in by_id
    ]


async def _collect_picker_tool_items(
    container: ContainerDep,
    *,
    include_mcp: bool,
    mcp_only: bool,
) -> list[ToolResponse]:
    tools_list = await container.tool_repository.list(limit=_TOOLS_MAX_LIMIT, offset=0)
    items: list[ToolResponse] = []
    seen_tool_ids: set[str] = set()
    for tool_row in tools_list:
        is_mcp = _is_mcp_tool_reference(tool_row)
        if mcp_only and not is_mcp:
            continue
        if not include_mcp and is_mcp:
            continue
        items.append(
            _enrich_tool_response_from_registry(
                container,
                _tool_response_from_reference(tool_row, agent_toolkit_ids=[]),
            )
        )
        seen_tool_ids.add(tool_row.tool_id)

    if not mcp_only:
        items.extend(
            _append_registry_tools(
                container,
                seen_tool_ids=seen_tool_ids,
            )
        )
    return items


def _picker_page(
    items: list[ToolResponse],
    *,
    limit: int,
    offset: int,
) -> OffsetPage[ToolResponse]:
    return OffsetPage[ToolResponse](
        items=items[offset : offset + limit],
        total=len(items),
        limit=limit,
        offset=offset,
    )


async def _visible_tool_picker_page(
    container: ContainerDep,
    items: list[ToolResponse],
    *,
    limit: int,
    offset: int,
    match: Callable[[ToolResponse], bool],
) -> OffsetPage[ToolResponse]:
    visible = await _filter_picker_items(
        container, [item for item in items if match(item)]
    )
    return _picker_page(visible, limit=limit, offset=offset)


async def _list_picker_tools_and_flows(
    container: ContainerDep,
    *,
    picker_category: PickerCategory,
    limit: int,
    offset: int,
    q: str | None = None,
) -> OffsetPage[ToolResponse]:
    needle = q.strip().lower() if isinstance(q, str) and q.strip() else None

    def _match(item: ToolResponse) -> bool:
        if needle is None:
            return True
        hay = " ".join(
            part
            for part in (
                item.tool_id,
                item.title or "",
                item.description or "",
            )
        ).lower()
        return needle in hay

    if picker_category == PickerCategory.FLOW:
        flow_items = [item for item in await _collect_picker_flow_items(container) if _match(item)]
        return _picker_page(flow_items, limit=limit, offset=offset)

    if picker_category == PickerCategory.MCP:
        tool_items = await _collect_picker_tool_items(
            container,
            include_mcp=True,
            mcp_only=True,
        )
        return await _visible_tool_picker_page(
            container, tool_items, limit=limit, offset=offset, match=_match
        )

    if picker_category == PickerCategory.CODE:
        tool_items = await _collect_picker_tool_items(
            container,
            include_mcp=False,
            mcp_only=False,
        )
        return await _visible_tool_picker_page(
            container, tool_items, limit=limit, offset=offset, match=_match
        )

    flow_items = [item for item in await _collect_picker_flow_items(container) if _match(item)]
    tool_items = await _collect_picker_tool_items(
        container,
        include_mcp=True,
        mcp_only=False,
    )
    visible_tools = await _filter_picker_items(
        container, [item for item in tool_items if _match(item)]
    )
    return _picker_page(flow_items + visible_tools, limit=limit, offset=offset)


@router.get("/", response_model=OffsetPage[ToolResponse])
async def list_tools(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_TOOLS_MAX_LIMIT, description="Максимум tools")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
) -> OffsetPage[ToolResponse]:
    """Список tools с пагинацией."""
    tools, total = await asyncio.gather(
        container.tool_repository.list(limit=limit, offset=offset),
        container.tool_repository.count_all(),
    )
    allowed_ids = set(
        await container.flow_access_service.filter_viewable_tool_ids(
            [tool_row.tool_id for tool_row in tools],
            user_id=_actor_user_id(),
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
        limit=limit,
        offset=offset,
    )


@router.get("/all", response_model=OffsetPage[ToolResponse])
async def list_all_tools_and_flows(
    container: ContainerDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=_TOOLS_ALL_HTTP_MAX_LIMIT,
            description="Максимум tools+flows на страницу (пагинация offset)",
        ),
    ] = _TOOLS_ALL_HTTP_MAX_LIMIT,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
    picker_category: Annotated[
        PickerCategory | None,
        Query(description="Категория для tool picker: all, code, flow, mcp"),
    ] = None,
    q: Annotated[
        str | None,
        Query(description="Поиск по tool_id / title / description"),
    ] = None,
) -> OffsetPage[ToolResponse]:
    """Список tools и flows для picker с общим лимитом."""
    return await _list_picker_tools_and_flows(
        container,
        picker_category=picker_category if picker_category is not None else PickerCategory.ALL,
        limit=limit,
        offset=offset,
        q=q,
    )


class ToolTagGroupResponse(StrictBaseModel):
    """Платформенное LLM-описание tag-группы tools."""

    tag: str
    description_ru: str
    description_en: str
    updated_at: str
    content_hash: str


@router.get("/tag-groups", response_model=OffsetPage[ToolTagGroupResponse])
async def list_tool_tag_groups(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_TAG_GROUPS_HTTP_MAX_LIMIT)] = _TAG_GROUPS_HTTP_MAX_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ToolTagGroupResponse]:
    """Список платформенных описаний групп tools по тегам."""
    groups = await container.tool_tag_group_service.list_groups(limit=limit, offset=offset)
    items = [
        ToolTagGroupResponse(
            tag=group.tag,
            description_ru=group.description_ru,
            description_en=group.description_en,
            updated_at=group.updated_at.isoformat(),
            content_hash=group.content_hash,
        )
        for group in groups
    ]
    # list_groups returns one page; total for OffsetPage is page+offset when short page ends.
    page_len = len(items)
    total = offset + page_len if page_len < limit else offset + page_len + 1
    return OffsetPage[ToolTagGroupResponse](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/preview", response_model=ToolPreviewResponse)
async def preview_tool(request: ToolPreviewRequest, container: ContainerDep) -> ToolPreviewResponse:
    """Dual preview: model-visible schema and server execution plan."""
    await _require_view_tool(container, request.tool_id)
    tool = _resolve_registry_tool(container, request.tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_id}' not found")
    return build_tool_preview(
        tool,
        binding_overrides=request.binding_overrides,
        model_args=request.model_args,
    )


@router.get("/{tool_id}/contract", response_model=ToolDefinition)
async def get_tool_contract(tool_id: str, container: ContainerDep) -> ToolDefinition:
    """ToolDefinition-shaped contract built from builtin BaseTool metadata."""
    await _require_view_tool(container, tool_id)
    tool = _resolve_registry_tool(container, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found in registry")
    return build_tool_definition_from_base_tool(tool)


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: str, container: ContainerDep) -> ToolResponse:
    """Получает tool по ID; при отсутствии в репозитории — flow или builtin registry."""
    await _require_view_tool_or_flow(container, tool_id)
    tool = await container.tool_repository.get(tool_id)
    if tool is not None:
        toolkit_ids = await _toolkit_ids_for_tool(container, tool.tool_id)
        return _enrich_tool_response_from_registry(
            container,
            _tool_response_from_reference(tool, agent_toolkit_ids=toolkit_ids),
        )
    registry_tool = _resolve_registry_tool(container, tool_id)
    if registry_tool is not None:
        return _tool_response_from_registry_tool(registry_tool)
    flow_cfg = await container.flow_repository.get(tool_id)
    if flow_cfg is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    flow_toolkit_ids = await _toolkit_ids_for_flow(container, flow_cfg.flow_id)
    flow_item = _flow_response(flow_cfg)
    return flow_item.model_copy(update={"agent_toolkit_ids": flow_toolkit_ids})


@router.post("/", response_model=ToolResponse)
async def create_tool(request: ToolCreateRequest, container: ContainerDep) -> ToolResponse:
    """Создает новый tool"""
    await _require_company_member(container)
    react_role = ReactToolRole(request.react_role) if request.react_role else ReactToolRole.STANDARD

    ps = request.parameters_schema
    raw_properties = ps.get("properties")
    if ps.get("type") != "object" or not isinstance(raw_properties, dict):
        raise HTTPException(
            status_code=422,
            detail="parameters_schema must be JSON Schema object with type: object and properties",
        )

    ref = ToolReference(
        tool_id=request.tool_id,
        title=request.title,
        description=request.description,
        code=request.code,
        language=request.language,
        entrypoint=request.entrypoint.strip()
        if request.entrypoint and request.entrypoint.strip()
        else None,
        parameters_schema=ps,
        tags=request.tags or [],
        react_role=react_role,
    )

    _ = await container.tool_repository.set(ref)
    ctx = require_context()
    if ctx.active_company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    await container.flow_access_service.sync_tool_saved(
        ref.tool_id,
        company_id=ctx.active_company.company_id,
        permission=ref.permission,
    )
    await set_tool_toolkit_membership(
        container.agent_toolkit_repository,
        tool_id=ref.tool_id,
        toolkit_ids=list(request.agent_toolkit_ids),
    )

    return _enrich_tool_response_from_registry(
        container,
        _tool_response_from_reference(
            ref,
            agent_toolkit_ids=list(request.agent_toolkit_ids),
        ),
    )


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, container: ContainerDep) -> dict[str, str]:
    """Удаляет tool"""
    await _require_view_tool(container, tool_id)
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    await container.flow_access_service.sync_tool_deleted(tool_id)
    return {"status": "deleted", "tool_id": tool_id}
