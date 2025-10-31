"""
Репозиторий для работы с MCP серверами.
Наследуется от Storage, поэтому имеет все его методы + типизированную работу с MCPServerConfig.
"""

import logging
from typing import Optional, List

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models.mcp_models import MCPServerConfig
from app.core.context import get_context

logger = logging.getLogger(__name__)


class MCPServerRepository(BaseRepository[MCPServerConfig]):
    """
    Репозиторий для MCP серверов с поддержкой мультитенантности.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с MCPServerConfig через Generic[MCPServerConfig].
    """

    def __init__(self, storage: Storage = None):
        # Передаем model_class=MCPServerConfig для типизации
        super().__init__(model_class=MCPServerConfig, storage=storage)
    
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
        """Получить MCP сервер компании с типизацией"""
        # MCP серверы имеют специальную логику с company_id в ключе
        # Поэтому формируем ключ вручную и используем Storage.get напрямую
        key = self._get_key(server_id, company_id)
        data = await super(BaseRepository, self).get(key)
        if data is None:
            return None

        try:
            return self.model_class.model_validate_json(data)
        except Exception as e:
            logger.error(f"Ошибка парсинга MCP сервера {server_id}: {e}")
            return None

    async def set(self, config: MCPServerConfig) -> bool:
        """Сохранить MCP сервер с типизацией"""
        # MCP серверы имеют специальную логику с company_id в ключе
        key = self._get_key(config.server_id, config.company_id)
        data = config.model_dump_json()
        return await super(BaseRepository, self).set(key, data)

    async def delete(self, server_id: str, company_id: Optional[str] = None) -> bool:
        """Удалить MCP сервер и все его тулы"""
        if company_id is None:
            company_id = self._get_company_id_from_context()

        # Удаляем все тулы этого сервера
        await self._delete_server_tools(server_id, company_id)

        # MCP серверы имеют специальную логику с company_id в ключе
        key = self._get_key(server_id, company_id)
        return await super(BaseRepository, self).delete(key)
    
    async def list_all(self, limit: int = 100, company_id: Optional[str] = None) -> List[MCPServerConfig]:
        """Список всех MCP серверов текущей компании (оптимизировано)"""
        # MCP серверы используют специфическую логику с company_id,
        # поэтому используем прямой подход вместо list_all_typed
        prefix = self._get_prefix(company_id)
        all_data = await self.get_all_by_prefix(prefix, limit=limit)  # Используем Storage метод напрямую

        servers = []
        for key, data in all_data.items():
            try:
                server = MCPServerConfig.model_validate_json(data)
                servers.append(server)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue

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

