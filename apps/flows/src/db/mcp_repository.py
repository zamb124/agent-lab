"""
Репозиторий для MCP серверов.
"""


from typing import override

from apps.flows.src.models.mcp import MCPServerConfig
from core.db import BaseRepository, Storage


class MCPServerRepository(BaseRepository[MCPServerConfig]):
    """
    Репозиторий для работы с MCP серверами.

    Хранит конфигурации MCP серверов в Storage.
    """

    is_global: bool = False
    owner_service: str = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, MCPServerConfig)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"mcp_server:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "mcp_server:"

    @override
    def _get_table_name(self) -> str:
        return "mcp_servers"

    @override
    def _extract_entity_id(self, entity: MCPServerConfig) -> str:
        return entity.server_id

    async def list_active(self) -> list[MCPServerConfig]:
        """Возвращает только активные серверы."""
        all_servers = await self.list(limit=1000)
        return [s for s in all_servers if s.is_active]

    async def get_by_id(self, server_id: str) -> MCPServerConfig | None:
        """Получает сервер по ID."""
        return await self.get(server_id)
