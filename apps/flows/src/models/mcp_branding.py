"""Глобальный branding MCP серверов по server_id (slug)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal, override

from oxyde import Field as DbField
from pydantic import BaseModel, ConfigDict, Field

from core.models.platform_model import PlatformModel

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


class MCPServerBranding(PlatformModel):
    """Иконка MCP сервера. Таблица ``mcp_server_branding`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "mcp_server_branding"

    server_id: str = DbField(db_pk=True, min_length=1, max_length=64)
    icon_file_id: str = DbField(min_length=1)
    updated_by_user_id: str = DbField(min_length=1)
    updated_at: datetime = DbField()

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.server_id == "" or self.icon_file_id == "" or self.updated_by_user_id == "":
            raise ValueError("server_id, icon_file_id and updated_by_user_id are required")
        self.updated_at = datetime.now(timezone.utc)


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
