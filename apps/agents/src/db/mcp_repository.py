"""
Репозиторий для MCP серверов.
"""

from typing import List, Optional

from apps.agents.src.models.mcp import MCPServerConfig
from core.db import BaseRepository, Storage


class MCPServerRepository(BaseRepository[MCPServerConfig]):
    """
    Репозиторий для работы с MCP серверами.
    
    Хранит конфигурации MCP серверов в Storage.
    """
    
    is_global = False
    owner_service = "agents"

    def __init__(self, storage: Storage):
        super().__init__(storage, MCPServerConfig)

    def _get_key(self, entity_id: str) -> str:
        return f"mcp_server:{entity_id}"
    
    def _get_prefix(self) -> str:
        return "mcp_server:"
    
    def _get_table_name(self) -> str:
        return "mcp_servers"

    def _extract_entity_id(self, entity: MCPServerConfig) -> str:
        return entity.server_id
    
    async def list_active(self) -> List[MCPServerConfig]:
        """Возвращает только активные серверы."""
        all_servers = await self.list_all()
        return [s for s in all_servers if s.is_active]
    
    async def get_by_id(self, server_id: str) -> Optional[MCPServerConfig]:
        """Получает сервер по ID."""
        return await self.get(server_id)
