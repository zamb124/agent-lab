"""Глобальный branding MCP серверов по server_id (slug)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["MCPServerBranding", "MCPServerBrandingResolved"]


class MCPServerBranding(BaseModel):
    """Иконка MCP сервера для всех компаний платформы."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    server_id: str = Field(..., description="Slug MCP сервера (server_id)")
    icon_file_id: str = Field(..., description="Публичный файл иконки (FileRecord.file_id)")
    updated_at: datetime = Field(..., description="Время последнего изменения")
    updated_by_user_id: str = Field(..., description="Кто обновил branding")


class MCPServerBrandingResolved(BaseModel):
    """Branding с вычисленным icon_url для API."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    server_id: str
    icon_file_id: str
    icon_url: str
    updated_at: datetime
    updated_by_user_id: str


class MCPBrandingManifestEntryPayload(BaseModel):
    """Строка entries в apps/flows/mcp_branding/manifest.yaml."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    server_id: str = Field(..., min_length=1)
    file: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    license: str = Field(..., min_length=1)


class MCPBrandingManifestFilePayload(BaseModel):
    """Корень apps/flows/mcp_branding/manifest.yaml."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    default_icon: str = Field(..., min_length=1)
    entries: list[MCPBrandingManifestEntryPayload] = Field(default_factory=list)
