"""
API endpoints для tools.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.agents.src.container import AgentContainer, get_container
from core.logging import get_logger
from apps.agents.src.models import ToolReference, CallParameter

logger = get_logger(__name__)

router = APIRouter(tags=["tools"])


async def get_container_dep() -> AgentContainer:
    """Dependency для получения контейнера"""
    return get_container()


class ToolCreateRequest(BaseModel):
    """Запрос на создание tool"""

    tool_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    args_schema: Optional[dict] = None
    tags: Optional[List[str]] = None


class ToolResponse(BaseModel):
    """Ответ с данными tool"""

    tool_id: str
    title: Optional[str]
    description: Optional[str]
    code: Optional[str] = None
    args_schema: Optional[dict] = None
    tags: List[str] = []
    permission: Optional[str | List[str]] = None
    item_type: str = "tool"  # tool или agent
    tool_type: Optional[str] = None  # tool, reason, exit
    code_mode: Optional[str] = None  # inline_code или mcp_tool
    mcp_server_id: Optional[str] = None  # ID MCP сервера


@router.get("/", response_model=List[ToolResponse])
async def list_tools(
    container: AgentContainer = Depends(get_container_dep),
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
            tags=t.tags or ["misc"],
            permission=t.permission,
            item_type="tool",
            tool_type=t.tool_type,
        )
        for t in tools
    ]


@router.get("/all", response_model=List[ToolResponse])
async def list_all_tools_and_agents(
    container: AgentContainer = Depends(get_container_dep),
) -> List[ToolResponse]:
    """Список всех tools и agents для picker"""
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
            tags=t.tags or ["misc"],
            permission=t.permission,
            item_type="tool",
            tool_type=t.tool_type,
            code_mode=t.code_mode.value if t.code_mode else None,
            mcp_server_id=t.mcp_server_id,
        ))
    
    # Agents (as tools)
    agents = await container.agent_repository.list_all()
    for a in agents:
        result.append(ToolResponse(
            tool_id=a.agent_id,
            title=a.name,
            description=a.description,
            tags=a.tags or ["agent"],
            permission=None,
            item_type="agent",
        ))
    
    return result


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: str, container: AgentContainer = Depends(get_container_dep)
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
        tags=tool.tags or ["misc"],
        permission=tool.permission,
        item_type="tool",
        tool_type=tool.tool_type,
    )


@router.post("/", response_model=ToolResponse)
async def create_tool(
    request: ToolCreateRequest, container: AgentContainer = Depends(get_container_dep)
) -> ToolResponse:
    """Создает новый tool"""
    args_schema: dict[str, CallParameter] = {}
    if request.args_schema:
        for param_name, param_def in request.args_schema.items():
            if isinstance(param_def, dict):
                args_schema[param_name] = CallParameter(
                    type=param_def.get("type", "string"),
                    description=param_def.get("description", ""),
                )
    
    ref = ToolReference(
        tool_id=request.tool_id,
        title=request.title,
        description=request.description,
        code=request.code,
        args_schema=args_schema,
        tags=request.tags or [],
    )

    await container.tool_repository.set(ref)

    return ToolResponse(
        tool_id=ref.tool_id,
        title=ref.title,
        description=ref.description,
        code=ref.code,
        args_schema=ref.args_schema if ref.args_schema else None,
        tags=ref.tags,
        tool_type=ref.tool_type,
    )


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str, container: AgentContainer = Depends(get_container_dep)
) -> dict:
    """Удаляет tool"""
    deleted = await container.tool_repository.delete(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "tool_id": tool_id}
