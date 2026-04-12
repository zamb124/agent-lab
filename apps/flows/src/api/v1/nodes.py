"""
API endpoints для nodes.
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.pagination import OffsetPage
from apps.flows.src.dependencies import ContainerDep
from core.logging import get_logger
from apps.flows.src.models import NodeConfig, ToolReference, NodeLLMOverride
from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.models.tool_reference import CallParameter

logger = get_logger(__name__)

router = APIRouter(tags=["nodes"])


class NodeLLMOverrideRequest(BaseModel):
    """Request для переопределения LLM настроек ноды."""
    
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class NodeCreateRequest(BaseModel):
    """Запрос на создание ноды"""

    node_id: str
    type: str  # llm_node, code, flow, remote_flow, external_api, mcp, channel
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    tools: List[Any] = []  # str для обычных tools, dict для inline tools
    llm: Optional[NodeLLMOverrideRequest] = None
    variables: Dict[str, Any] = {}
    tags: List[str] = []


class NodeResponse(BaseModel):
    """Ответ с данными ноды"""

    node_id: str
    type: str
    name: str
    description: Optional[str]
    prompt: Optional[str]
    tools: List[Any]  # str для обычных tools, dict для inline tools
    llm: Optional[Dict[str, Any]]
    variables: Dict[str, Any] = {}
    tags: List[str] = []
    source: str = "manual"


def _tool_ref_to_response(tool_ref: ToolReference) -> Any:
    """Конвертирует ToolReference в формат для ответа."""
    if tool_ref.code:
        result = {
            "tool_id": tool_ref.tool_id,
            "description": tool_ref.description,
            "code": tool_ref.code,
        }
        if tool_ref.args_schema:
            result["args_schema"] = {
                k: {"type": v.type, "description": v.description}
                for k, v in tool_ref.args_schema.items()
            }
        if tool_ref.parameters_schema:
            result["parameters_schema"] = tool_ref.parameters_schema
        return result
    return tool_ref.tool_id


def _convert_inline_tool(tool_data: Dict[str, Any]) -> ToolReference:
    """Конвертирует inline tool dict в ToolReference."""
    args_schema = {}
    if "args_schema" in tool_data:
        for k, v in tool_data["args_schema"].items():
            args_schema[k] = CallParameter(
                type=v.get("type", "string"),
                description=v.get("description", ""),
                required=v.get("required", True),
            )
    
    react_role_raw = tool_data.get("react_role")
    react_role = (
        ReactToolRole(react_role_raw)
        if react_role_raw
        else ReactToolRole.STANDARD
    )

    return ToolReference(
        tool_id=tool_data["tool_id"],
        description=tool_data.get("description"),
        code=tool_data.get("code"),
        args_schema=args_schema,
        parameters_schema=tool_data.get("parameters_schema"),
        react_role=react_role,
    )


def _node_to_response(node: NodeConfig) -> NodeResponse:
    """Конвертирует NodeConfig в NodeResponse"""
    return NodeResponse(
        node_id=node.node_id,
        type=node.type,
        name=node.name,
        description=node.description,
        prompt=node.prompt,
        tools=[_tool_ref_to_response(t) for t in node.tools],
        llm=node.llm_override.model_dump() if node.llm_override else None,
        variables=node.local_variables,
        tags=node.tags,
        source=node.source,
    )


@router.get("/", response_model=OffsetPage[NodeResponse])
async def list_nodes(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[NodeResponse]:
    nodes, total = await asyncio.gather(
        container.node_repository.list(limit=limit, offset=offset),
        container.node_repository.count_all(),
    )
    items = [_node_to_response(n) for n in nodes]
    return OffsetPage[NodeResponse](items=items, total=total, limit=limit, offset=offset)


@router.post("/", response_model=NodeResponse)
async def create_node(
    request: NodeCreateRequest, container: ContainerDep
) -> NodeResponse:
    """Создает новую ноду"""
    tools = []
    for tool_ref in request.tools:
        if isinstance(tool_ref, dict):
            tools.append(_convert_inline_tool(tool_ref))
        else:
            tool = await container.tool_repository.get(tool_ref)
            if tool is None:
                node = await container.node_repository.get(tool_ref)
                if node is None:
                    raise HTTPException(status_code=400, detail=f"Tool '{tool_ref}' not found")
            tools.append(ToolReference(tool_id=tool_ref))

    llm_config = None
    if request.llm:
        llm_config = LLMConfig(**request.llm.model_dump())

    node_config = NodeConfig(
        node_id=request.node_id,
        type=request.type,
        name=request.name,
        description=request.description,
        prompt=request.prompt,
        tools=tools,
        llm_config=llm_config,
        local_variables=request.variables,
        tags=request.tags,
        source="api",
    )

    await container.node_repository.set(node_config)

    return _node_to_response(node_config)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: str, container: ContainerDep
) -> NodeResponse:
    """Получает ноду по ID"""
    node = await container.node_repository.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return _node_to_response(node)


@router.put("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    request: NodeCreateRequest,
    container: ContainerDep,
) -> NodeResponse:
    """Обновляет или создаёт ноду (upsert)"""
    existing = await container.node_repository.get(node_id)
    source = existing.source if existing else "api"

    tools = []
    for tool_ref in request.tools:
        if isinstance(tool_ref, dict):
            tools.append(_convert_inline_tool(tool_ref))
        else:
            if tool_ref != node_id:
                tool = await container.tool_repository.get(tool_ref)
                if tool is None:
                    node = await container.node_repository.get(tool_ref)
                    if node is None:
                        raise HTTPException(status_code=400, detail=f"Tool '{tool_ref}' not found")
            tools.append(ToolReference(tool_id=tool_ref))

    llm_config = None
    if request.llm:
        llm_config = LLMConfig(**request.llm.model_dump())

    node_config = NodeConfig(
        node_id=node_id,
        type=request.type,
        name=request.name,
        description=request.description,
        prompt=request.prompt,
        tools=tools,
        llm_config=llm_config,
        local_variables=request.variables,
        tags=request.tags,
        source=source,
    )

    await container.node_repository.set(node_config)

    return _node_to_response(node_config)


@router.delete("/{node_id}")
async def delete_node(
    node_id: str, container: ContainerDep
) -> dict:
    """Удаляет ноду"""
    deleted = await container.node_repository.delete(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "deleted", "node_id": node_id}
