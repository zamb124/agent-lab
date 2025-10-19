"""
API endpoints для управления MCP серверами.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.models.mcp_models import MCPServerConfig
from app.frontend.dependencies import StorageDep
from app.db.repositories.mcp_repository import MCPServerRepository
from app.core.mcp_sync import sync_mcp_server_tools

router = APIRouter(prefix="/api/v1/mcp", tags=["MCP"])


@router.get("/servers")
async def list_mcp_servers(storage: StorageDep) -> List[MCPServerConfig]:
    """Список всех MCP серверов текущей компании"""
    mcp_repo = MCPServerRepository(storage)
    return await mcp_repo.list_all()


@router.get("/servers/{server_id}")
async def get_mcp_server(server_id: str, storage: StorageDep) -> MCPServerConfig:
    """Получить MCP сервер по ID"""
    mcp_repo = MCPServerRepository(storage)
    server = await mcp_repo.get(server_id)
    
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    return server


@router.post("/servers")
async def create_mcp_server(
    server_config: MCPServerConfig,
    storage: StorageDep
) -> MCPServerConfig:
    """Создать новый MCP сервер"""
    mcp_repo = MCPServerRepository(storage)
    
    # Проверяем что сервер с таким ID не существует
    existing = await mcp_repo.get(server_config.server_id)
    if existing:
        raise HTTPException(status_code=400, detail="MCP сервер с таким ID уже существует")
    
    # Сохраняем
    await mcp_repo.set(server_config)
    
    return server_config


@router.put("/servers/{server_id}")
async def update_mcp_server(
    server_id: str,
    server_config: MCPServerConfig,
    storage: StorageDep
) -> MCPServerConfig:
    """Обновить MCP сервер"""
    if server_id != server_config.server_id:
        raise HTTPException(status_code=400, detail="ID сервера не совпадает")
    
    mcp_repo = MCPServerRepository(storage)
    
    # Проверяем что сервер существует
    existing = await mcp_repo.get(server_id)
    if not existing:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    # Сохраняем
    await mcp_repo.set(server_config)
    
    return server_config


@router.delete("/servers/{server_id}")
async def delete_mcp_server(server_id: str, storage: StorageDep) -> Dict[str, Any]:
    """Удалить MCP сервер и все его тулы"""
    mcp_repo = MCPServerRepository(storage)
    
    # Проверяем что сервер существует
    existing = await mcp_repo.get(server_id)
    if not existing:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    # Удаляем
    success = await mcp_repo.delete(server_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось удалить MCP сервер")
    
    return {"success": True, "message": f"MCP сервер {server_id} удален"}


@router.post("/servers/{server_id}/sync")
async def sync_server(server_id: str, storage: StorageDep) -> Dict[str, Any]:
    """
    Синхронизировать тулы MCP сервера.
    
    Подключается к MCP серверу, получает список тулов и сохраняет в БД.
    """
    mcp_repo = MCPServerRepository(storage)
    
    # Проверяем что сервер существует
    existing = await mcp_repo.get(server_id)
    if not existing:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    try:
        tools = await sync_mcp_server_tools(server_id)
        
        return {
            "success": True,
            "tools_count": len(tools),
            "tools": [
                {
                    "tool_id": t.tool_id,
                    "title": t.title,
                    "description": t.description
                }
                for t in tools
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


@router.post("/servers/{server_id}/test")
async def test_mcp_server(server_id: str, storage: StorageDep) -> Dict[str, Any]:
    """
    Протестировать подключение к MCP серверу.
    
    Пытается получить список тулов для проверки корректности настроек.
    """
    from app.core.mcp_client import get_mcp_client
    
    mcp_repo = MCPServerRepository(storage)
    
    # Проверяем что сервер существует
    server_config = await mcp_repo.get(server_id)
    if not server_config:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    try:
        # Получаем клиент и пытаемся получить список тулов
        client = await get_mcp_client(server_id)
        tools = await client.list_tools()
        
        return {
            "success": True,
            "message": "Подключение успешно",
            "tools_count": len(tools),
            "transport_type": server_config.transport_type,
            "url": server_config.url
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка подключения: {str(e)}",
            "transport_type": server_config.transport_type,
            "url": server_config.url
        }

