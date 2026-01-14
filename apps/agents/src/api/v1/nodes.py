"""
API endpoints для nodes.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.agents.src.container import AgentContainer, get_container
from core.logging import get_logger
from apps.agents.src.models import NodeConfig, ToolReference, NodeLLMOverride
from apps.agents.src.models.tool_reference import CallParameter

logger = get_logger(__name__)

router = APIRouter(tags=["nodes"])


async def get_container_dep() -> AgentContainer:
    """Dependency для получения контейнера"""
    return get_container()


class NodeLLMOverrideRequest(BaseModel):
    """Request для переопределения LLM настроек ноды."""
    
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class NodeCreateRequest(BaseModel):
    """Запрос на создание ноды"""

    node_id: str
    type: str  # react_node, function, tool, agent, remote_agent, external_api
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
        return result
    return tool_ref.tool_id


def _convert_inline_tool(tool_data: Dict[str, Any]) -> ToolReference:
    """Конвертирует inline tool dict в ToolReference."""
    args_schema = {}
    if "args_schema" in tool_data:
        for k, v in tool_data["args_schema"].items():
            args_schema[k] = CallParameter(
                type=v.get("type", "string"), 
                description=v.get("description", "")
            )
    
    return ToolReference(
        tool_id=tool_data["tool_id"],
        description=tool_data.get("description"),
        code=tool_data.get("code"),
        args_schema=args_schema,
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


@router.get("/", response_model=List[NodeResponse])
async def list_nodes(
    container: AgentContainer = Depends(get_container_dep),
) -> List[NodeResponse]:
    """Список всех нод"""
    nodes = await container.node_repository.list_all()
    return [_node_to_response(n) for n in nodes]


@router.post("/", response_model=NodeResponse)
async def create_node(
    request: NodeCreateRequest, container: AgentContainer = Depends(get_container_dep)
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
    node_id: str, container: AgentContainer = Depends(get_container_dep)
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
    container: AgentContainer = Depends(get_container_dep),
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
    node_id: str, container: AgentContainer = Depends(get_container_dep)
) -> dict:
    """Удаляет ноду"""
    deleted = await container.node_repository.delete(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "deleted", "node_id": node_id}
