"""Сервис глобального branding MCP серверов."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import HTTPException

from apps.flows.src.db.mcp_catalog_repository import MCPCatalogRepository
from apps.flows.src.db.mcp_server_branding_repository import MCPServerBrandingRepository
from apps.flows.src.models.mcp_branding import MCPServerBranding, MCPServerBrandingResolved
from apps.flows.src.services.mcp_branding_aliases import (
    BRANDING_SERVER_ID_ALIASES,
    resolve_branding_server_id,
)
from core.context import get_context, require_context
from core.files.service import FilesService

_SERVER_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")

_ALLOWED_ICON_CONTENT_TYPES = frozenset({
    "image/png",
    "image/webp",
    "image/svg+xml",
    "image/jpeg",
})


class MCPServerBrandingService:
    """CRUD branding MCP и resolve icon_url для MCPServerResponse."""

    def __init__(
        self,
        *,
        branding_repository: MCPServerBrandingRepository,
        catalog_repository: MCPCatalogRepository,
        files_service: FilesService,
    ) -> None:
        self._branding_repository: MCPServerBrandingRepository = branding_repository
        self._catalog_repository: MCPCatalogRepository = catalog_repository
        self._files_service: FilesService = files_service

    @staticmethod
    def _require_system_company() -> None:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise HTTPException(status_code=403, detail="MCP branding is system company only")
        if ctx.active_company.company_id != "system":
            raise HTTPException(status_code=403, detail="MCP branding is system company only")

    @staticmethod
    def _validate_server_id(server_id: str) -> str:
        stripped = server_id.strip()
        if not _SERVER_ID_PATTERN.match(stripped):
            raise HTTPException(
                status_code=400,
                detail=f"server_id {stripped!r} is not a valid MCP slug",
            )
        return stripped

    async def _resolve_icon_url(self, icon_file_id: str) -> str:
        record = await self._files_service.get(icon_file_id)
        if not record.is_public:
            raise HTTPException(
                status_code=400,
                detail=f"File {icon_file_id} must be public for MCP branding",
            )
        if record.content_type not in _ALLOWED_ICON_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File content_type {record.content_type!r} is not allowed for MCP icon",
            )
        return record.url

    async def _to_resolved(self, branding: MCPServerBranding) -> MCPServerBrandingResolved:
        icon_url = await self._resolve_icon_url(branding.icon_file_id)
        return MCPServerBrandingResolved(
            server_id=branding.server_id,
            icon_file_id=branding.icon_file_id,
            icon_url=icon_url,
            updated_at=branding.updated_at,
            updated_by_user_id=branding.updated_by_user_id,
        )

    async def list_branding(self) -> list[MCPServerBrandingResolved]:
        entries = await self._branding_repository.list(limit=10_000)
        items: list[MCPServerBrandingResolved] = []
        for entry in entries:
            items.append(await self._to_resolved(entry))
        return items

    async def list_catalog_slugs(self) -> list[str]:
        entries = await self._catalog_repository.list(limit=10_000)
        slugs = sorted({entry.catalog_id for entry in entries})
        return slugs

    async def build_icon_url_map(self) -> dict[str, str]:
        entries = await self._branding_repository.list(limit=10_000)
        icon_map: dict[str, str] = {}
        for entry in entries:
            icon_map[entry.server_id] = await self._resolve_icon_url(entry.icon_file_id)
        for alias_server_id, canonical_server_id in BRANDING_SERVER_ID_ALIASES.items():
            canonical_url = icon_map.get(canonical_server_id)
            if canonical_url is not None and alias_server_id not in icon_map:
                icon_map[alias_server_id] = canonical_url
        return icon_map

    async def get_icon_url(self, server_id: str) -> str | None:
        branding = await self._branding_repository.get(server_id)
        if branding is None:
            canonical_server_id = resolve_branding_server_id(server_id)
            if canonical_server_id != server_id:
                branding = await self._branding_repository.get(canonical_server_id)
        if branding is None:
            return None
        return await self._resolve_icon_url(branding.icon_file_id)

    async def upsert_branding(self, server_id: str, icon_file_id: str) -> MCPServerBrandingResolved:
        self._require_system_company()
        normalized_server_id = self._validate_server_id(server_id)
        if not icon_file_id.strip():
            raise HTTPException(status_code=400, detail="icon_file_id is required")
        icon_url = await self._resolve_icon_url(icon_file_id.strip())
        ctx = require_context()
        now = datetime.now(UTC)
        branding = MCPServerBranding(
            server_id=normalized_server_id,
            icon_file_id=icon_file_id.strip(),
            updated_at=now,
            updated_by_user_id=ctx.user.user_id,
        )
        _ = await self._branding_repository.set(branding)
        return MCPServerBrandingResolved(
            server_id=branding.server_id,
            icon_file_id=branding.icon_file_id,
            icon_url=icon_url,
            updated_at=branding.updated_at,
            updated_by_user_id=branding.updated_by_user_id,
        )

    async def delete_branding(self, server_id: str) -> None:
        self._require_system_company()
        normalized_server_id = self._validate_server_id(server_id)
        existing = await self._branding_repository.get(normalized_server_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"MCP branding {normalized_server_id} not found")
        _ = await self._branding_repository.delete(normalized_server_id)
