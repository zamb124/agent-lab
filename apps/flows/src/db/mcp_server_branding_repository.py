"""Глобальный репозиторий branding MCP серверов."""

from __future__ import annotations

from typing import ClassVar, override

from apps.flows.src.models.mcp_branding import MCPServerBranding
from core.db import BaseRepository, Storage


class MCPServerBrandingRepository(BaseRepository[MCPServerBranding]):
    """Иконки MCP по server_id — одна запись на slug для всей платформы."""

    is_global: ClassVar[bool] = True
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, MCPServerBranding)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"mcp_server_branding:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "mcp_server_branding:"

    @override
    def _get_table_name(self) -> str:
        return "mcp_server_branding"

    @override
    def _extract_entity_id(self, entity: MCPServerBranding) -> str:
        return entity.server_id
