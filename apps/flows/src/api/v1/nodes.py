"""
API endpoints для nodes.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import NodeConfig, ToolReference
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeLLMConfig
from core.llm_context import LLMContextPatch
from core.logging import get_logger
from core.pagination import OffsetPage
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)

router = APIRouter(tags=["nodes"])


class NodeCreateRequest(BaseModel):
    """Запрос на создание ноды"""

    node_id: str
    type: NodeType
    name: str
    description: str | None = None
    prompt: str | None = None
    tools: list[str | ToolReference] = Field(default_factory=list)
    llm: NodeLLMConfig | None = None
    llm_context: LLMContextPatch | None = None
    llm_context_resource_key: str | None = None
    variables: JsonObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class NodeResponse(BaseModel):
    """Ответ с данными ноды"""

    node_id: str
    type: str
    name: str
    description: str | None
    prompt: str | None
    tools: list[str | JsonObject]
    llm: JsonObject | None
    llm_context: JsonObject | None = None
    llm_context_resource_key: str | None = None
    variables: JsonObject = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"


def _tool_ref_to_response(tool_ref: ToolReference) -> str | JsonObject:
    """Конвертирует ToolReference в формат для ответа."""
    if tool_ref.code:
        result: JsonObject = {
            "tool_id": tool_ref.tool_id,
            "description": tool_ref.description,
            "code": tool_ref.code,
        }
        if tool_ref.parameters_schema:
            result["parameters_schema"] = tool_ref.parameters_schema
        return result
    return tool_ref.tool_id


def _node_to_response(node: NodeConfig) -> NodeResponse:
    """Конвертирует NodeConfig в NodeResponse"""
    return NodeResponse(
        node_id=node.node_id,
        type=node.type.value,
        name=node.name,
        description=node.description,
        prompt=node.prompt,
        tools=[_tool_ref_to_response(t) for t in node.tools],
        llm=parse_json_object(node.llm.model_dump_json(exclude_none=True), "node.llm")
        if node.llm
        else None,
        llm_context=(
            parse_json_object(
                node.llm_context.model_dump_json(exclude_none=True), "node.llm_context"
            )
            if node.llm_context
            else None
        ),
        llm_context_resource_key=node.llm_context_resource_key,
        variables=node.local_variables,
        tags=node.tags,
        source=node.source,
    )


@router.get("/", response_model=OffsetPage[NodeResponse])
async def list_nodes(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NodeResponse]:
    nodes, total = await asyncio.gather(
        container.node_repository.list(limit=limit, offset=offset),
        container.node_repository.count_all(),
    )
    items = [_node_to_response(n) for n in nodes]
    return OffsetPage[NodeResponse](items=items, total=total, limit=limit, offset=offset)


@router.post("/", response_model=NodeResponse)
async def create_node(request: NodeCreateRequest, container: ContainerDep) -> NodeResponse:
    """Создает новую ноду"""
    tools: list[ToolReference] = []
    for tool_ref in request.tools:
        if isinstance(tool_ref, ToolReference):
            tools.append(tool_ref)
            continue

        tool = await container.tool_repository.get(tool_ref)
        if tool is None:
            node = await container.node_repository.get(tool_ref)
            if node is None:
                raise HTTPException(status_code=400, detail=f"Tool '{tool_ref}' not found")
        tools.append(ToolReference(tool_id=tool_ref))

    node_config = NodeConfig(
        node_id=request.node_id,
        type=request.type,
        name=request.name,
        description=request.description or "",
        prompt=request.prompt,
        tools=tools,
        llm=request.llm,
        llm_context=request.llm_context,
        llm_context_resource_key=request.llm_context_resource_key,
        local_variables=request.variables,
        tags=request.tags,
        source="api",
    )

    _ = await container.node_repository.set(node_config)

    return _node_to_response(node_config)


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: str, container: ContainerDep) -> NodeResponse:
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

    tools: list[ToolReference] = []
    for tool_ref in request.tools:
        if isinstance(tool_ref, ToolReference):
            tools.append(tool_ref)
            continue

        if tool_ref != node_id:
            tool = await container.tool_repository.get(tool_ref)
            if tool is None:
                node = await container.node_repository.get(tool_ref)
                if node is None:
                    raise HTTPException(status_code=400, detail=f"Tool '{tool_ref}' not found")
        tools.append(ToolReference(tool_id=tool_ref))

    node_config = NodeConfig(
        node_id=node_id,
        type=request.type,
        name=request.name,
        description=request.description or "",
        prompt=request.prompt,
        tools=tools,
        llm=request.llm,
        llm_context=request.llm_context,
        llm_context_resource_key=request.llm_context_resource_key,
        local_variables=request.variables,
        tags=request.tags,
        source=source,
    )

    _ = await container.node_repository.set(node_config)

    return _node_to_response(node_config)


@router.delete("/{node_id}")
async def delete_node(node_id: str, container: ContainerDep) -> dict[str, str]:
    """Удаляет ноду"""
    deleted = await container.node_repository.delete(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "deleted", "node_id": node_id}
