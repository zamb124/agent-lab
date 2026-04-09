"""
API endpoints для tools.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.flows.src.dependencies import ContainerDep
from core.logging import get_logger
from apps.flows.src.models import ToolReference, CallParameter
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.tools.json_schema_parameters import call_parameters_to_parameters_schema

logger = get_logger(__name__)

router = APIRouter(tags=["tools"])


class ToolCreateRequest(BaseModel):
    """Запрос на создание tool"""

    tool_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    args_schema: Optional[dict] = None
    parameters_schema: Optional[dict] = None
    tags: Optional[List[str]] = None
    react_role: Optional[str] = None


class ToolResponse(BaseModel):
    """Ответ с данными tool"""

    tool_id: str
    title: Optional[str]
    description: Optional[str]
    code: Optional[str] = None
    args_schema: Optional[dict] = None
    parameters_schema: Optional[dict] = None
    tags: List[str] = []
    permission: Optional[str | List[str]] = None
    item_type: str = "tool"  # tool или flow (запись из репозитория flows)
    react_role: Optional[str] = None
    code_mode: Optional[str] = None  # inline_code или mcp_tool
    mcp_server_id: Optional[str] = None  # ID MCP сервера


@router.get("/", response_model=List[ToolResponse])
async def list_tools(
    container: ContainerDep,
) -> List[ToolResponse]:
    """Список всех tools"""
    tools = await container.tool_repository.list_all()
    return [
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
        )
        for t in tools
    ]


@router.get("/all", response_model=List[ToolResponse])
async def list_all_tools_and_flows(
    container: ContainerDep,
) -> List[ToolResponse]:
    """Список всех tools и flows для picker."""
    result = []
    
    # Tools
    tools = await container.tool_repository.list_all()
    for t in tools:
        result.append(ToolResponse(
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
        ))
    
    # Flows (как объекты выбора в picker рядом с tools)
    flows = await container.flow_repository.list_all()
    for flow_row in flows:
        result.append(ToolResponse(
            tool_id=flow_row.flow_id,
            title=flow_row.name,
            description=flow_row.description,
            tags=flow_row.tags or ["flow"],
            permission=None,
            item_type="flow",
        ))
    
    return result


class DraftParametersSchemaRequest(BaseModel):
    """Черновик JSON Schema для LLM из legacy args_schema (CallParameter)."""

    args_schema: dict


class DraftParametersSchemaResponse(BaseModel):
    parameters_schema: dict


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
    """Получает tool по ID"""
    tool = await container.tool_repository.get(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
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
) -> dict:
    """Удаляет tool"""
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}
