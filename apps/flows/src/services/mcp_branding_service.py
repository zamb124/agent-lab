"""Сервис глобального branding MCP серверов."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from apps.flows.src.models.mcp_branding import MCPServerBranding, MCPServerBrandingResolved
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry
from apps.flows.src.services.mcp_branding_aliases import (
    BRANDING_SERVER_ID_ALIASES,
    resolve_branding_server_id,
)
from apps.flows.src.services.mcp_defaults import build_default_mcp_servers
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
    """CRUD branding MCP и resolve icon_url для MCPServerConfig."""

    def __init__(
        self,
        *,
        files_service: FilesService,
    ) -> None:
        self._files_service: FilesService = files_service

    @staticmethod
    def _require_system_company() -> None:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise PermissionError("MCP branding is system company only")
        if ctx.active_company.company_id != "system":
            raise PermissionError("MCP branding is system company only")

    @staticmethod
    def _validate_server_id(server_id: str) -> str:
        stripped = server_id.strip()
        if not _SERVER_ID_PATTERN.match(stripped):
            raise ValueError(f"server_id {stripped!r} is not a valid MCP slug")
        return stripped

    async def _resolve_icon_url(self, icon_file_id: str) -> str:
        record = await self._files_service.get(icon_file_id)
        if not record.is_public:
            raise ValueError(f"File {icon_file_id} must be public for MCP branding")
        if record.content_type not in _ALLOWED_ICON_CONTENT_TYPES:
            raise ValueError(
                f"File content_type {record.content_type!r} is not allowed for MCP icon"
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

    async def list_branding_by_server_id_asc(
        self,
        *,
        search: str,
        limit: int,
        offset: int,
    ) -> tuple[list[MCPServerBrandingResolved], int]:
        entries = await MCPServerBranding.list(limit=10_000)
        query = search.strip().casefold()
        if query:
            entries = [entry for entry in entries if query in entry.server_id.casefold()]
        entries.sort(key=lambda entry: entry.server_id.casefold())
        total = len(entries)
        page = entries[offset : offset + limit]
        items: list[MCPServerBrandingResolved] = []
        for entry in page:
            items.append(await self._to_resolved(entry))
        return items, total

    async def suggest_branding_slugs(self, *, search: str, limit: int) -> list[str]:
        entries = await MCPCatalogEntry.list(limit=10_000)
        default_server_ids = [server.server_id for server in build_default_mcp_servers()]
        slugs = sorted({*default_server_ids, *(entry.catalog_id for entry in entries)}, key=str.casefold)
        query = search.strip().casefold()
        if query:
            slugs = [slug for slug in slugs if query in slug.casefold()]
        return slugs[:limit]

    async def build_icon_url_map(self) -> dict[str, str]:
        entries = await MCPServerBranding.list(limit=10_000)
        icon_map: dict[str, str] = {}
        for entry in entries:
            icon_map[entry.server_id] = await self._resolve_icon_url(entry.icon_file_id)
        for alias_server_id, canonical_server_id in BRANDING_SERVER_ID_ALIASES.items():
            canonical_url = icon_map.get(canonical_server_id)
            if canonical_url is not None and alias_server_id not in icon_map:
                icon_map[alias_server_id] = canonical_url
        return icon_map

    async def build_icon_url_map_for_server_ids(
        self,
        server_ids: list[str],
    ) -> dict[str, str]:
        if not server_ids:
            return {}
        unique_ids = list(dict.fromkeys(server_ids))
        icon_map: dict[str, str] = {}
        for server_id in unique_ids:
            icon_url = await self.get_icon_url(server_id)
            if icon_url is not None:
                icon_map[server_id] = icon_url
        return icon_map

    async def get_icon_url(self, server_id: str) -> str | None:
        branding = await MCPServerBranding.get(server_id)
        if branding is None:
            canonical_server_id = resolve_branding_server_id(server_id)
            if canonical_server_id != server_id:
                branding = await MCPServerBranding.get(canonical_server_id)
        if branding is None:
            return None
        return await self._resolve_icon_url(branding.icon_file_id)

    async def upsert_branding(self, server_id: str, icon_file_id: str) -> MCPServerBrandingResolved:
        self._require_system_company()
        normalized_server_id = self._validate_server_id(server_id)
        if not icon_file_id.strip():
            raise ValueError("icon_file_id is required")
        icon_url = await self._resolve_icon_url(icon_file_id.strip())
        ctx = require_context()
        now = datetime.now(UTC)
        branding = MCPServerBranding(
            server_id=normalized_server_id,
            icon_file_id=icon_file_id.strip(),
            updated_at=now,
            updated_by_user_id=ctx.user.user_id,
        )
        _ = await MCPServerBranding.set(branding)
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
        existing = await MCPServerBranding.get(normalized_server_id)
        if existing is None:
            raise LookupError(f"MCP branding {normalized_server_id} not found")
        _ = await MCPServerBranding.delete_by_id(normalized_server_id)
