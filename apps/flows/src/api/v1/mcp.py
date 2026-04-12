"""
API endpoints для MCP серверов.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.pagination import OffsetPage
from apps.flows.src.clients.mcp_client import (
    MCPClientError,
    MCPHttpClient,
    clear_mcp_client_cache,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.mcp import MCPServerConfig, MCPToolInfo, MCPTransportType
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["mcp"])


class MCPServerCreateRequest(BaseModel):
    """Запрос на создание MCP сервера."""
    
    server_id: str = Field(
        ..., 
        description="Уникальный ID сервера",
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        min_length=2,
        max_length=64
    )
    name: str = Field(..., description="Название сервера")
    url: str = Field(..., description="URL MCP сервера")
    transport_type: MCPTransportType = Field(
        default=MCPTransportType.HTTP,
        description="Тип транспорта"
    )
    headers: dict = Field(default_factory=dict, description="HTTP headers")
    description: Optional[str] = Field(default=None, description="Описание")


class MCPServerUpdateRequest(BaseModel):
    """Запрос на обновление MCP сервера."""
    
    name: Optional[str] = None
    url: Optional[str] = None
    transport_type: Optional[str] = None
    headers: Optional[dict] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class MCPServerResponse(BaseModel):
    """Ответ с данными MCP сервера."""
    
    server_id: str
    name: str
    url: str
    transport_type: str
    headers: dict
    is_active: bool
    cached_tools: List[str]
    last_sync_at: Optional[datetime]
    description: Optional[str]


class MCPToolResponse(BaseModel):
    """Информация о tool."""
    
    name: str
    description: Optional[str]
    input_schema: Optional[dict]


class MCPSyncResponse(BaseModel):
    """Результат синхронизации."""
    
    success: bool
    tools_count: int
    tools: List[MCPToolResponse]


class MCPTestResponse(BaseModel):
    """Результат теста подключения."""
    
    success: bool
    message: str
    tools_count: int
    transport_type: str
    url: str


def _server_to_response(server: MCPServerConfig) -> MCPServerResponse:
    """Конвертирует MCPServerConfig в response."""
    return MCPServerResponse(
        server_id=server.server_id,
        name=server.name,
        url=server.url,
        transport_type=server.transport_type.value,
        headers=server.headers,
        is_active=server.is_active,
        cached_tools=server.cached_tools,
        last_sync_at=server.last_sync_at,
        description=server.description,
    )


@router.get("/servers", response_model=OffsetPage[MCPServerResponse])
async def list_servers(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[MCPServerResponse]:
    servers, total = await asyncio.gather(
        container.mcp_server_repository.list(limit=limit, offset=offset),
        container.mcp_server_repository.count_all(),
    )
    items = [_server_to_response(s) for s in servers]
    return OffsetPage[MCPServerResponse](items=items, total=total, limit=limit, offset=offset)


@router.post("/servers", response_model=MCPServerResponse)
async def create_server(
    request: MCPServerCreateRequest,
    container: ContainerDep,
) -> MCPServerResponse:
    """Создает MCP сервер."""
    existing = await container.mcp_server_repository.get(request.server_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Server {request.server_id} already exists"
        )
    
    server = MCPServerConfig(
        server_id=request.server_id,
        name=request.name,
        url=request.url,
        transport_type=request.transport_type,
        headers=request.headers,
        description=request.description,
    )
    
    await container.mcp_server_repository.set(server)
    logger.info(f"MCP server created: {request.server_id}")
    
    return _server_to_response(server)


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str,
    container: ContainerDep,
) -> MCPServerResponse:
    """Получает MCP сервер по ID."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    return _server_to_response(server)


@router.put("/servers/{server_id}", response_model=MCPServerResponse)
async def update_server(
    server_id: str,
    request: MCPServerUpdateRequest,
    container: ContainerDep,
) -> MCPServerResponse:
    """Обновляет MCP сервер."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    update_data = request.model_dump(exclude_unset=True)
    
    # Конвертируем transport_type строку в enum
    if "transport_type" in update_data and update_data["transport_type"]:
        from apps.flows.src.models.mcp import MCPTransportType
        update_data["transport_type"] = MCPTransportType(update_data["transport_type"])
    
    for field, value in update_data.items():
        setattr(server, field, value)
    
    await container.mcp_server_repository.set(server)
    clear_mcp_client_cache(server_id)
    
    logger.info(f"MCP server updated: {server_id}")
    return _server_to_response(server)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    container: ContainerDep,
) -> dict:
    """Удаляет MCP сервер."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # Удаляем связанные tools
    for tool_id in server.cached_tools:
        await container.tool_repository.delete(tool_id)
    
    await container.mcp_server_repository.delete(server_id)
    clear_mcp_client_cache(server_id)
    
    logger.info(f"MCP server deleted: {server_id}")
    return {"status": "deleted", "server_id": server_id}


@router.post("/servers/{server_id}/sync", response_model=MCPSyncResponse)
async def sync_server_tools(
    server_id: str,
    container: ContainerDep,
) -> MCPSyncResponse:
    """
    Синхронизирует tools с MCP сервера.
    
    Получает список tools через tools/list и сохраняет в ToolRepository.
    """
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # Переменные нужны только если в headers есть @var: ссылки
    variables: Dict[str, Any] = {}
    has_var_refs = any("@var:" in str(v) for v in server.headers.values())
    if has_var_refs:
        variables = await container.variables_service.get_all_resolved_vars()
    
    client = MCPHttpClient(server, variables)
    
    try:
        tools = await client.list_tools()
    except MCPClientError as e:
        raise HTTPException(status_code=502, detail=f"MCP server error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}")
    
    # Сохраняем tools в репозиторий
    from apps.flows.src.models import ToolReference
    from apps.flows.src.models.enums import CodeMode
    from apps.flows.src.models.tool_reference import CallParameter
    
    tool_ids = []
    for tool in tools:
        tool_id = f"mcp:{server_id}:{tool.name}"
        tool_ids.append(tool_id)
        
        # Конвертируем JSON Schema в формат CallParameter
        args_schema = {}
        if tool.input_schema:
            properties = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            for param_name, param_info in properties.items():
                args_schema[param_name] = CallParameter(
                    type=param_info.get("type", "string"),
                    description=param_info.get("description", ""),
                    required=param_name in required,
                )
        
        tool_ref = ToolReference(
            tool_id=tool_id,
            title=tool.name,
            description=tool.description or f"MCP tool: {tool.name}",
            code_mode=CodeMode.MCP_TOOL,
            args_schema=args_schema,
            tags=["mcp", f"mcp:{server_id}"],
            mcp_server_id=server_id,
            mcp_tool_name=tool.name,
        )
        await container.tool_repository.set(tool_ref)
    
    # Удаляем старые tools которых больше нет
    for old_tool_id in server.cached_tools:
        if old_tool_id not in tool_ids:
            await container.tool_repository.delete(old_tool_id)
    
    # Обновляем server
    server.cached_tools = tool_ids
    server.last_sync_at = datetime.now(timezone.utc)
    await container.mcp_server_repository.set(server)
    
    logger.info(f"MCP server {server_id}: synced {len(tools)} tools")
    
    return MCPSyncResponse(
        success=True,
        tools_count=len(tools),
        tools=[
            MCPToolResponse(
                name=t.name,
                description=t.description,
                input_schema=t.input_schema,
            )
            for t in tools
        ],
    )


@router.post("/servers/{server_id}/test", response_model=MCPTestResponse)
async def test_server_connection(
    server_id: str,
    container: ContainerDep,
) -> MCPTestResponse:
    """Тестирует подключение к MCP серверу."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    # Переменные нужны только если в headers есть @var: ссылки
    variables: Dict[str, Any] = {}
    has_var_refs = any("@var:" in str(v) for v in server.headers.values())
    if has_var_refs:
        variables = await container.variables_service.get_all_resolved_vars()
    
    client = MCPHttpClient(server, variables)
    
    try:
        await client.initialize()
        tools = await client.list_tools()
    except MCPClientError as e:
        raise HTTPException(status_code=502, detail=f"MCP server error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}")
    
    return MCPTestResponse(
        success=True,
        message="Connection successful",
        tools_count=len(tools),
        transport_type=server.transport_type.value,
        url=server.url,
    )
