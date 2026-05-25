"""
API endpoints для MCP серверов.
"""

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.flows.src.clients.mcp_client import (
    MCPClient,
    MCPClientError,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType
from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from core.logging import get_logger
from core.pagination import OffsetPage
from core.types import JsonObject, JsonValue

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
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    description: str | None = Field(default=None, description="Описание")


class MCPServerUpdateRequest(BaseModel):
    """Запрос на обновление MCP сервера."""

    name: str | None = None
    url: str | None = None
    transport_type: MCPTransportType | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None
    description: str | None = None


class MCPServerResponse(BaseModel):
    """Ответ с данными MCP сервера."""

    server_id: str
    name: str
    url: str
    transport_type: str
    headers: dict[str, str]
    is_active: bool
    cached_tools: list[str]
    last_sync_at: datetime | None
    description: str | None


class MCPToolResponse(BaseModel):
    """Информация о tool."""

    name: str
    title: str | None
    description: str | None
    parameters_schema: JsonObject
    output_schema: JsonObject | None
    schema_hash: str
    schema_version: str


class MCPSyncResponse(BaseModel):
    """Результат синхронизации."""

    success: bool
    tools_count: int
    tools: list[MCPToolResponse]


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
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
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

    _ = await container.mcp_server_repository.set(server)
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

    if request.name is not None:
        server.name = request.name
    if request.url is not None:
        server.url = request.url
    if request.transport_type is not None:
        server.transport_type = MCPTransportType(request.transport_type)
    if request.headers is not None:
        server.headers = request.headers
    if request.is_active is not None:
        server.is_active = request.is_active
    if request.description is not None:
        server.description = request.description

    _ = await container.mcp_server_repository.set(server)
    logger.info(f"MCP server updated: {server_id}")
    return _server_to_response(server)


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    container: ContainerDep,
) -> dict[str, str]:
    """Удаляет MCP сервер."""
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # Удаляем связанные tools
    for tool_id in server.cached_tools:
        _ = await container.tool_repository.delete(tool_id)

    _ = await container.mcp_server_repository.delete(server_id)
    logger.info(f"MCP server deleted: {server_id}")
    return {"status": "deleted", "server_id": server_id}


@router.post("/servers/{server_id}/sync", response_model=MCPSyncResponse)
async def sync_server_tools(
    server_id: str,
    container: ContainerDep,
) -> MCPSyncResponse:
    """
    Синхронизирует tools с MCP сервера.

    Та же логика, что и при авто-синхронизации (`apps.flows.src.services.mcp_sync`).
    """
    server = await container.mcp_server_repository.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        _tool_ids, tools = await sync_mcp_server_tools(container=container, server_config=server)
    except MCPClientError as e:
        raise HTTPException(status_code=502, detail=f"MCP server error: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}") from e

    logger.info("MCP server %s: synced %s tools", server_id, len(tools))

    return MCPSyncResponse(
        success=True,
        tools_count=len(tools),
        tools=[
            MCPToolResponse(
                name=t.tool_name,
                title=t.title,
                description=t.description,
                parameters_schema=t.parameters_schema,
                output_schema=t.output_schema,
                schema_hash=t.schema_hash,
                schema_version=t.schema_version,
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
    variables: Mapping[str, JsonValue] = {}
    has_var_refs = any("@var:" in str(v) for v in server.headers.values())
    if has_var_refs:
        variables = await container.variables_service.get_all_resolved_vars()

    client = MCPClient(server, variables)

    try:
        _ = await client.initialize()
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
