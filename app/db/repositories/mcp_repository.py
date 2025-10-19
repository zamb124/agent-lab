"""
Репозиторий для работы с MCP серверами.
"""

import logging
from typing import Optional, List

from app.db.repositories.base import BaseRepository
from app.models.mcp_models import MCPServerConfig
from app.core.context import get_context

logger = logging.getLogger(__name__)


class MCPServerRepository(BaseRepository[MCPServerConfig]):
    """Репозиторий для MCP серверов с поддержкой мультитенантности"""
    
    def _get_key(self, server_id: str, company_id: Optional[str] = None) -> str:
        """
        Формирует ключ: mcp_server:{company_id}:{server_id}
        
        Если company_id не передан, берет из контекста.
        """
        if company_id is None:
            company_id = self._get_company_id_from_context()
        
        return f"mcp_server:{company_id}:{server_id}"
    
    def _get_prefix(self, company_id: Optional[str] = None) -> str:
        """Префикс для поиска серверов компании"""
        if company_id is None:
            company_id = self._get_company_id_from_context()
        
        return f"mcp_server:{company_id}:"
    
    async def get(self, server_id: str, company_id: Optional[str] = None) -> Optional[MCPServerConfig]:
        """Получить MCP сервер компании"""
        key = self._get_key(server_id, company_id)
        data = await self.storage.get(key)
        if data:
            try:
                return MCPServerConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга MCP сервера {server_id}: {e}")
                return None
        return None
    
    async def set(self, config: MCPServerConfig) -> bool:
        """Сохранить MCP сервер"""
        key = self._get_key(config.server_id, config.company_id)
        data = config.model_dump_json()
        return await self.storage.set(key, data)
    
    async def delete(self, server_id: str, company_id: Optional[str] = None) -> bool:
        """Удалить MCP сервер и все его тулы"""
        key = self._get_key(server_id, company_id)
        
        if company_id is None:
            company_id = self._get_company_id_from_context()
        
        # Удаляем все тулы этого сервера
        await self._delete_server_tools(server_id, company_id)
        
        return await self.storage.delete(key)
    
    async def list_all(self, limit: int = 100, company_id: Optional[str] = None) -> List[MCPServerConfig]:
        """Список всех MCP серверов текущей компании"""
        prefix = self._get_prefix(company_id)
        keys = await self.storage.list_by_prefix(prefix, limit=limit)
        
        servers = []
        for key in keys:
            data = await self.storage.get(key)
            if data:
                try:
                    server = MCPServerConfig.model_validate_json(data)
                    servers.append(server)
                except Exception as e:
                    logger.error(f"Ошибка парсинга {key}: {e}")
        
        return servers
    
    async def list_active(self, limit: int = 100, company_id: Optional[str] = None) -> List[MCPServerConfig]:
        """Список активных MCP серверов компании"""
        all_servers = await self.list_all(limit=limit, company_id=company_id)
        return [s for s in all_servers if s.is_active]
    
    def _get_company_id_from_context(self) -> str:
        """Получить company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Не удалось определить company_id из контекста")
        return context.active_company.company_id
    
    async def _delete_server_tools(self, server_id: str, company_id: str):
        """Удаляет все тулы MCP сервера"""
        # Ищем все тулы с префиксом tool:mcp:server_id:
        tool_prefix = f"tool:mcp:{server_id}:"
        tool_keys = await self.storage.list_by_prefix(tool_prefix, limit=1000)
        
        deleted_count = 0
        for tool_key in tool_keys:
            await self.storage.delete(tool_key)
            deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"🗑️ Удалено {deleted_count} MCP тулов для сервера {server_id}")

