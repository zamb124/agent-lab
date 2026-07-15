"""
API endpoints для tools.
"""

import asyncio
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig, ToolReference, flow_tool_parameters_schema
from apps.flows.src.models.enums import CodeMode, ReactToolRole
from apps.flows.src.services.agent_toolkit_service import (
    get_toolkit_ids_for_flow,
    get_toolkit_ids_for_tool,
    set_tool_toolkit_membership,
)
from apps.flows.src.tools.base import BaseTool
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.types import JsonObject

logger = get_logger(__name__)

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


def _tool_response_from_registry_tool(tool: BaseTool) -> ToolResponse:
    return ToolResponse(
        tool_id=tool.name,
        title=tool.name,
        description=tool.description,
        code=None,
        language="python",
        entrypoint=None,
        parameters_schema=tool.parameters,
        tags=tool.get_tags(),
        permission=tool.permission,
        item_type="tool",
        react_role=tool.react_role.value,
        code_mode=None,
        mcp_server_id=None,
        mcp_tool_name=None,
    )


def _flow_response(flow_row: FlowConfig) -> ToolResponse:
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


async def _collect_picker_flow_items(container: ContainerDep) -> tuple[list[ToolResponse], int]:
    flows_list, flows_count = await asyncio.gather(
        container.flow_repository.list(limit=_TOOLS_MAX_LIMIT),
        container.flow_repository.count_all(),
    )
    return [_flow_response(flow_row) for flow_row in flows_list], flows_count


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
        items.append(_tool_response_from_reference(tool_row, agent_toolkit_ids=[]))
        seen_tool_ids.add(tool_row.tool_id)

    if not mcp_only:
        items.extend(
            _append_registry_tools(
                container,
                seen_tool_ids=seen_tool_ids,
            )
        )
    return items


async def _list_picker_tools_and_flows(
    container: ContainerDep,
    *,
    picker_category: PickerCategory,
    limit: int,
    offset: int,
) -> OffsetPage[ToolResponse]:
    if picker_category == PickerCategory.FLOW:
        flow_items, flows_count = await _collect_picker_flow_items(container)
        page = flow_items[offset : offset + limit]
        return OffsetPage[ToolResponse](
            items=page,
            total=flows_count,
            limit=limit,
            offset=offset,
        )

    if picker_category == PickerCategory.MCP:
        tool_items = await _collect_picker_tool_items(
            container,
            include_mcp=True,
            mcp_only=True,
        )
        page = tool_items[offset : offset + limit]
        return OffsetPage[ToolResponse](
            items=page,
            total=len(tool_items),
            limit=limit,
            offset=offset,
        )

    if picker_category == PickerCategory.CODE:
        tool_items = await _collect_picker_tool_items(
            container,
            include_mcp=False,
            mcp_only=False,
        )
        page = tool_items[offset : offset + limit]
        return OffsetPage[ToolResponse](
            items=page,
            total=len(tool_items),
            limit=limit,
            offset=offset,
        )

    flow_items, flows_count = await _collect_picker_flow_items(container)
    tool_items = await _collect_picker_tool_items(
        container,
        include_mcp=True,
        mcp_only=False,
    )
    merged_items = flow_items + tool_items
    page = merged_items[offset : offset + limit]
    return OffsetPage[ToolResponse](
        items=page,
        total=flows_count + len(tool_items),
        limit=limit,
        offset=offset,
    )


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
    response_items: list[ToolResponse] = []
    for tool_row in tools:
        toolkit_ids = await _toolkit_ids_for_tool(container, tool_row.tool_id)
        response_items.append(
            _tool_response_from_reference(tool_row, agent_toolkit_ids=toolkit_ids)
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
        Query(ge=1, le=_TOOLS_MAX_LIMIT, description="Максимум tools+flows вместе"),
    ] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
    picker_category: Annotated[
        PickerCategory | None,
        Query(description="Категория для tool picker: all, code, flow, mcp"),
    ] = None,
) -> OffsetPage[ToolResponse]:
    """Список tools и flows для picker с общим лимитом."""
    if picker_category is not None:
        return await _list_picker_tools_and_flows(
            container,
            picker_category=picker_category,
            limit=limit,
            offset=offset,
        )

    tools_list, flows_list, tools_count, flows_count = await asyncio.gather(
        container.tool_repository.list(limit=_TOOLS_MAX_LIMIT, offset=0),
        container.flow_repository.list(limit=_TOOLS_MAX_LIMIT),
        container.tool_repository.count_all(),
        container.flow_repository.count_all(),
    )
    items: list[ToolResponse] = []
    seen_tool_ids: set[str] = set()
    for t in tools_list:
        toolkit_ids = await _toolkit_ids_for_tool(container, t.tool_id)
        items.append(_tool_response_from_reference(t, agent_toolkit_ids=toolkit_ids))
        seen_tool_ids.add(t.tool_id)

    registry = container.tool_registry
    registry.register_builtin_tools()
    registry_only_count = 0
    for tool_id, tool in sorted(registry.list_all().items(), key=lambda item: item[0]):
        if tool_id in seen_tool_ids:
            continue
        if not tool.listed_in_platform_tool_docs:
            continue
        items.append(_tool_response_from_registry_tool(tool))
        seen_tool_ids.add(tool_id)
        registry_only_count += 1

    for flow_row in flows_list:
        flow_toolkit_ids = await _toolkit_ids_for_flow(container, flow_row.flow_id)
        flow_item = _flow_response(flow_row)
        items.append(flow_item.model_copy(update={"agent_toolkit_ids": flow_toolkit_ids}))

    page = items[offset : offset + limit]
    return OffsetPage[ToolResponse](
        items=page,
        total=tools_count + flows_count + registry_only_count,
        limit=limit,
        offset=offset,
    )


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: str, container: ContainerDep) -> ToolResponse:
    """Получает tool по ID; при отсутствии в репозитории — flow с тем же id."""
    tool = await container.tool_repository.get(tool_id)
    if tool is not None:
        toolkit_ids = await _toolkit_ids_for_tool(container, tool.tool_id)
        return _tool_response_from_reference(tool, agent_toolkit_ids=toolkit_ids)
    flow_cfg = await container.flow_repository.get(tool_id)
    if flow_cfg is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    flow_toolkit_ids = await _toolkit_ids_for_flow(container, flow_cfg.flow_id)
    flow_item = _flow_response(flow_cfg)
    return flow_item.model_copy(update={"agent_toolkit_ids": flow_toolkit_ids})


@router.post("/", response_model=ToolResponse)
async def create_tool(request: ToolCreateRequest, container: ContainerDep) -> ToolResponse:
    """Создает новый tool"""
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
    await set_tool_toolkit_membership(
        container.agent_toolkit_repository,
        tool_id=ref.tool_id,
        toolkit_ids=list(request.agent_toolkit_ids),
    )

    return _tool_response_from_reference(
        ref,
        agent_toolkit_ids=list(request.agent_toolkit_ids),
    )


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, container: ContainerDep) -> dict[str, str]:
    """Удаляет tool"""
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}
