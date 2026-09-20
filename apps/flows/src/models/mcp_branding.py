"""Глобальный branding MCP серверов по server_id (slug)."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MCPServerBranding",
    "MCPServerBrandingDeletedResponse",
    "MCPServerBrandingIdPayload",
    "MCPServerBrandingListPayload",
    "MCPServerBrandingResolved",
    "MCPServerBrandingSlugSuggestPayload",
    "MCPServerBrandingSlugSuggestResponse",
    "MCPServerBrandingUpsertPayload",
    "MCPServerBrandingUpsertRequest",
]


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


class MCPServerBrandingListPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    search: str = ""
    limit: int = Field(default=40, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MCPServerBrandingSlugSuggestPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    search: str = ""
    limit: int = Field(default=15, ge=1, le=50)


class MCPServerBrandingIdPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    server_id: str = Field(..., min_length=1)


class MCPServerBrandingUpsertRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    icon_file_id: str = Field(..., min_length=1)


class MCPServerBrandingUpsertPayload(MCPServerBrandingUpsertRequest):
    server_id: str = Field(..., min_length=1)


class MCPServerBrandingDeletedResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: Literal["deleted"]
    server_id: str


class MCPServerBrandingSlugSuggestResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    slugs: list[str]


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
