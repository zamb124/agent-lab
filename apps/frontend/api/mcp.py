"""
API endpoints для управления MCP серверами
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.agents.container import get_agents_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp-api"])


class MCPServerCreate(BaseModel):
    name: str
    url: str
    description: Optional[str] = None
    transport_type: str = "http"
    headers: Dict[str, str] = {}
    timeout: int = 30
    is_active: bool = True
    auto_sync_tools: bool = True


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    transport_type: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[int] = None
    is_active: Optional[bool] = None
    auto_sync_tools: Optional[bool] = None


@router.get("/servers")
async def list_servers():
    """Получить список всех MCP серверов"""
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    servers = await mcp_repo.list_all()
    return [_server_to_dict(s) for s in servers]


@router.get("/servers/{server_id}")
async def get_server(server_id: str):
    """Получить MCP сервер по ID"""
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server = await mcp_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    return _server_to_dict(server)


@router.post("/servers")
async def create_server(data: MCPServerCreate):
    """Создать новый MCP сервер"""
    from apps.agents.models import MCPServerConfig
    from core.utils import generate_slug
    
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server_id = f"mcp_{generate_slug(data.name, add_hash=True)}"
    
    server = MCPServerConfig(
        server_id=server_id,
        name=data.name,
        url=data.url,
        description=data.description,
        transport_type=data.transport_type,
        headers=data.headers,
        timeout=data.timeout,
        is_active=data.is_active,
        auto_sync_tools=data.auto_sync_tools,
        cached_tools=[],
    )
    
    await mcp_repo.set(server)
    
    return _server_to_dict(server)


@router.put("/servers/{server_id}")
async def update_server(server_id: str, data: MCPServerUpdate):
    """Обновить MCP сервер"""
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server = await mcp_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(server, key, value)
    
    await mcp_repo.set(server)
    
    return _server_to_dict(server)


@router.delete("/servers/{server_id}")
async def delete_server(server_id: str):
    """Удалить MCP сервер"""
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server = await mcp_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    await mcp_repo.delete(server_id)
    
    return {"status": "deleted", "server_id": server_id}


@router.post("/servers/{server_id}/sync")
async def sync_server(server_id: str):
    """Синхронизировать инструменты MCP сервера"""
    from apps.agents.services.mcp_sync import sync_mcp_server
    
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server = await mcp_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    result = await sync_mcp_server(server)
    
    return result


@router.post("/servers/{server_id}/test")
async def test_server(server_id: str):
    """Тестовое подключение к MCP серверу"""
    from apps.agents.services.mcp_client import MCPClient
    
    agents_container = get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    server = await mcp_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    try:
        client = MCPClient(server)
        tools = await client.list_tools()
        
        return {
            "status": "success",
            "tools_count": len(tools),
            "tools": [{"name": t.name, "description": t.description} for t in tools[:10]]
        }
    except Exception as e:
        logger.error(f"Ошибка тестирования MCP сервера {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _server_to_dict(server) -> Dict[str, Any]:
    """Конвертировать MCPServerConfig в dict"""
    return {
        "server_id": server.server_id,
        "name": server.name,
        "url": server.url,
        "description": server.description,
        "transport_type": server.transport_type,
        "headers": server.headers,
        "timeout": server.timeout,
        "is_active": server.is_active,
        "auto_sync_tools": server.auto_sync_tools,
        "cached_tools": server.cached_tools,
        "last_sync_at": server.last_sync_at.isoformat() if server.last_sync_at else None,
    }

