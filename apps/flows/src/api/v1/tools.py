"""
API endpoints для tools.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import CallParameter, ToolReference
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.json_schema_parameters import call_parameters_to_parameters_schema
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter(tags=["tools"])
JsonDict = dict[str, Any]


class ToolCreateRequest(BaseModel):
    """Запрос на создание tool"""

    tool_id: str
    title: str | None = None
    description: str | None = None
    code: str | None = None
    args_schema: JsonDict | None = None
    parameters_schema: JsonDict | None = None
    tags: list[str] | None = None
    react_role: str | None = None


class ToolResponse(BaseModel):
    """Ответ с данными tool"""

    tool_id: str
    title: str | None
    description: str | None
    code: str | None = None
    args_schema: JsonDict | None = None
    parameters_schema: JsonDict | None = None
    tags: list[str] = Field(default_factory=list)
    permission: str | list[str] | None = None
    item_type: str = "tool"  # tool или flow (запись из репозитория flows)
    react_role: str | None = None
    code_mode: str | None = None  # inline_code или mcp_tool
    mcp_server_id: str | None = None  # ID MCP сервера
    mcp_tool_name: str | None = None  # имя tool на MCP (если id не mcp:…)


_TOOLS_MAX_LIMIT = 2000


@router.get("/", response_model=OffsetPage[ToolResponse])
async def list_tools(
    container: ContainerDep,
    limit: int = Query(500, ge=1, le=_TOOLS_MAX_LIMIT, description="Максимум tools"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
) -> OffsetPage[ToolResponse]:
    """Список tools с пагинацией."""
    tools, total = await asyncio.gather(
        container.tool_repository.list(limit=limit, offset=offset),
        container.tool_repository.count_all(),
    )
    return OffsetPage[ToolResponse](
        items=[
            ToolResponse(
                tool_id=t.tool_id,
                title=t.title,
                description=t.description,
                code=t.code,
                args_schema=t.args_schema if t.args_schema else None,
                parameters_schema=t.parameters_schema,
                tags=t.tags or ["misc"],
                permission=t.permission,
                item_type="tool",
                react_role=t.react_role.value,
                code_mode=t.code_mode.value if t.code_mode else None,
                mcp_server_id=t.mcp_server_id,
                mcp_tool_name=t.mcp_tool_name,
            )
            for t in tools
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/all", response_model=OffsetPage[ToolResponse])
async def list_all_tools_and_flows(
    container: ContainerDep,
    limit: int = Query(500, ge=1, le=_TOOLS_MAX_LIMIT, description="Максимум tools+flows вместе"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
) -> OffsetPage[ToolResponse]:
    """Список tools и flows для picker с общим лимитом."""
    tools_list, flows_list, tools_count, flows_count = await asyncio.gather(
        container.tool_repository.list(limit=limit, offset=offset),
        container.flow_repository.list(limit=limit),
        container.tool_repository.count_all(),
        container.flow_repository.count_all(),
    )
    items = []
    for t in tools_list:
        items.append(ToolResponse(
            tool_id=t.tool_id,
            title=t.title,
            description=t.description,
            code=t.code,
            args_schema=t.args_schema if t.args_schema else None,
            parameters_schema=t.parameters_schema,
            tags=t.tags or ["misc"],
            permission=t.permission,
            item_type="tool",
            react_role=t.react_role.value,
            code_mode=t.code_mode.value if t.code_mode else None,
            mcp_server_id=t.mcp_server_id,
            mcp_tool_name=t.mcp_tool_name,
        ))
    for flow_row in flows_list:
        items.append(ToolResponse(
            tool_id=flow_row.flow_id,
            title=flow_row.name,
            description=flow_row.description,
            tags=flow_row.tags or ["flow"],
            permission=None,
            item_type="flow",
        ))
    return OffsetPage[ToolResponse](
        items=items,
        total=tools_count + flows_count,
        limit=limit,
        offset=offset,
    )


class DraftParametersSchemaRequest(BaseModel):
    """Черновик JSON Schema для LLM из legacy args_schema (CallParameter)."""

    args_schema: JsonDict


class DraftParametersSchemaResponse(BaseModel):
    parameters_schema: JsonDict


@router.post(
    "/draft-parameters-schema",
    response_model=DraftParametersSchemaResponse,
)
async def draft_parameters_schema(
    container: ContainerDep,
    request: DraftParametersSchemaRequest,
) -> DraftParametersSchemaResponse:
    _ = container
    if not request.args_schema:
        raise HTTPException(
            status_code=422,
            detail="args_schema must not be empty",
        )
    args_schema: dict[str, CallParameter] = {}
    for param_name, param_def in request.args_schema.items():
        if isinstance(param_def, dict):
            args_schema[param_name] = CallParameter(
                type=param_def.get("type", "string"),
                description=param_def.get("description", ""),
                required=param_def.get("required", True),
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"args_schema.{param_name} must be an object",
            )
    parameters_schema = call_parameters_to_parameters_schema(args_schema)
    return DraftParametersSchemaResponse(parameters_schema=parameters_schema)


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: str, container: ContainerDep
) -> ToolResponse:
    """Получает tool по ID; при отсутствии в репозитории — flow с тем же id."""
    tool = await container.tool_repository.get(tool_id)
    if tool is not None:
        return ToolResponse(
            tool_id=tool.tool_id,
            title=tool.title,
            description=tool.description,
            code=tool.code,
            args_schema=tool.args_schema if tool.args_schema else None,
            parameters_schema=tool.parameters_schema,
            tags=tool.tags or ["misc"],
            permission=tool.permission,
            item_type="tool",
            react_role=tool.react_role.value,
            code_mode=tool.code_mode.value if tool.code_mode else None,
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
async def create_tool(
    request: ToolCreateRequest, container: ContainerDep
) -> ToolResponse:
    """Создает новый tool"""
    args_schema: dict[str, CallParameter] = {}
    if request.args_schema:
        for param_name, param_def in request.args_schema.items():
            if isinstance(param_def, dict):
                args_schema[param_name] = CallParameter(
                    type=param_def.get("type", "string"),
                    description=param_def.get("description", ""),
                    required=param_def.get("required", True),
                )

    react_role = (
        ReactToolRole(request.react_role)
        if request.react_role
        else ReactToolRole.STANDARD
    )

    ps = request.parameters_schema
    if ps is not None and (
        not isinstance(ps, dict) or ps.get("type") != "object" or "properties" not in ps
    ):
        raise HTTPException(
            status_code=422,
            detail="parameters_schema must be JSON Schema object with type: object and properties",
        )

    ref = ToolReference(
        tool_id=request.tool_id,
        title=request.title,
        description=request.description,
        code=request.code,
        parameters_schema=ps,
        args_schema=args_schema,
        tags=request.tags or [],
        react_role=react_role,
    )

    await container.tool_repository.set(ref)

    return ToolResponse(
        tool_id=ref.tool_id,
        title=ref.title,
        description=ref.description,
        code=ref.code,
        args_schema=ref.args_schema if ref.args_schema else None,
        parameters_schema=ref.parameters_schema,
        tags=ref.tags,
        react_role=ref.react_role.value,
    )


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str, container: ContainerDep
) -> dict[str, str]:
    """Удаляет tool"""
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}
