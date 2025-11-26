"""
Репозиторий для работы с MCP серверами.
Использует service БД, is_global=False (изолирован по компаниям).
"""

import logging
from typing import Optional, List

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models.mcp_models import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPServerRepository(BaseRepository[MCPServerConfig]):
    """
    Репозиторий для MCP серверов.
    is_global=False - MCP серверы изолированы по компаниям.
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=MCPServerConfig)
    
    def _get_key(self, server_id: str) -> str:
        return f"mcp_server:{server_id}"
    
    def _get_prefix(self) -> str:
        return "mcp_server:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: MCPServerConfig) -> str:
        return entity.server_id
    
    async def list_active(self, limit: int = 100) -> List[MCPServerConfig]:
        """
        Список активных MCP серверов компании.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список активных серверов
        """
        all_servers = await self.list_all(limit=limit)
        return [s for s in all_servers if s.is_active]
    
    async def delete(self, server_id: str) -> bool:
        """
        Удаляет MCP сервер и все его тулы.
        
        Args:
            server_id: ID сервера
            
        Returns:
            True если удаление успешно
        """
        await self._delete_server_tools(server_id)
        return await super().delete(server_id)
    
    async def _delete_server_tools(self, server_id: str):
        """Удаляет все тулы MCP сервера"""
        tool_prefix = f"tool:mcp:{server_id}:"
        final_tool_prefix = self._build_final_key(tool_prefix)
        table_name = self._get_table_name()
        
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_tool_prefix, table_name, limit=1000
        )
        
        deleted_count = 0
        for tool_key in all_data.keys():
            await self._storage._delete_with_table(tool_key, table_name)
            deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"Удалено {deleted_count} MCP тулов для сервера {server_id}")
