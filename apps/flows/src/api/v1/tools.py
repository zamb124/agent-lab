"""
API endpoints для tools.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig, ToolReference
from apps.flows.src.models.enums import ReactToolRole
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


_TOOLS_MAX_LIMIT = 2000


def _tool_response_from_reference(t: ToolReference) -> ToolResponse:
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
        tags=flow_row.tags or ["flow"],
        permission=None,
        item_type="flow",
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
    return OffsetPage[ToolResponse](
        items=[_tool_response_from_reference(t) for t in tools],
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
) -> OffsetPage[ToolResponse]:
    """Список tools и flows для picker с общим лимитом."""
    tools_list, flows_list, tools_count, flows_count = await asyncio.gather(
        container.tool_repository.list(limit=_TOOLS_MAX_LIMIT, offset=0),
        container.flow_repository.list(limit=_TOOLS_MAX_LIMIT),
        container.tool_repository.count_all(),
        container.flow_repository.count_all(),
    )
    items: list[ToolResponse] = []
    seen_tool_ids: set[str] = set()
    for t in tools_list:
        items.append(_tool_response_from_reference(t))
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
        items.append(_flow_response(flow_row))

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
        return ToolResponse(
            tool_id=tool.tool_id,
            title=tool.title,
            description=tool.description,
            code=tool.code,
            language=tool.language,
            entrypoint=tool.entrypoint,
            parameters_schema=tool.parameters_schema,
            tags=tool.tags or ["misc"],
            permission=tool.permission,
            item_type="tool",
            react_role=tool.react_role.value,
            code_mode=tool.code_mode.value,
            mcp_server_id=tool.mcp_server_id,
            mcp_tool_name=tool.mcp_tool_name,
        )
    flow_cfg = await container.flow_repository.get(tool_id)
    if flow_cfg is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return ToolResponse(
        tool_id=flow_cfg.flow_id,
        title=flow_cfg.name,
        description=flow_cfg.description,
        tags=list(flow_cfg.tags) if flow_cfg.tags else ["flow"],
        permission=list(flow_cfg.permission) if flow_cfg.permission else None,
        item_type="flow",
    )


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

    return ToolResponse(
        tool_id=ref.tool_id,
        title=ref.title,
        description=ref.description,
        code=ref.code,
        language=ref.language,
        entrypoint=ref.entrypoint,
        parameters_schema=ref.parameters_schema,
        tags=ref.tags,
        react_role=ref.react_role.value,
    )


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, container: ContainerDep) -> dict[str, str]:
    """Удаляет tool"""
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}
