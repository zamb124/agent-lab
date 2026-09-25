"""
Модели для MCP (Model Context Protocol).

MCP серверы подключаются по HTTP и предоставляют tools для агентов.
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.context.context import require_active_company
from core.integrations.mcp import MCPDiscoveredTool, MCPInitializeResult, MCPToolDefinition
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject

__all__ = [
    "MCPCallResult",
    "MCPDiscoveredTool",
    "MCPInitializeResult",
    "MCPServerConfig",
    "MCPServerDeletedResponse",
    "MCPServerIdPayload",
    "MCPServerListPayload",
    "MCPServerSource",
    "MCPServerUpdatePayload",
    "MCPServerUpdateRequest",
    "MCPSyncResponse",
    "MCPTestResponse",
    "MCPToolDefinition",
    "MCPTransportType",
]


class MCPServerSource(str, Enum):
    """Источник конфигурации MCP сервера в компании."""

    PLATFORM = "platform"
    CATALOG = "catalog"
    MANUAL = "manual"


class MCPTransportType(str, Enum):
    """Тип транспорта MCP сервера."""

    HTTP = "http"
    SSE = "sse"


class MCPServerConfig(CompanyScopedModel):
    """MCP-сервер компании. Таблица ``mcp_servers`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "mcp_servers"
        unique_together: list[tuple[str, str]] = [("company_id", "server_id")]

    server_id: str = DbField(
        min_length=2,
        max_length=64,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        db_index=True,
        description="Уникальный идентификатор сервера",
    )
    name: str = DbField(min_length=1, description="Отображаемое имя сервера")
    url: str = DbField(min_length=1, description="URL MCP сервера (JSON-RPC endpoint)")
    company_id: str = DbField(default="", db_index=True)
    mcp_server_id: str = DbField(default="", db_pk=True)
    transport_type: MCPTransportType = DbField(
        default=MCPTransportType.HTTP,
        description="Тип транспорта: http или sse",
    )
    headers: dict[str, str] = DbField(
        default_factory=dict,
        description="HTTP headers, поддерживает @var: ссылки",
    )
    propagate_platform_context: bool = DbField(default=False)
    request_timeout_seconds: int | None = DbField(default=None)
    is_active: bool = DbField(default=True, description="Активен ли сервер")
    cached_tools: list[str] = DbField(
        default_factory=list,
        description="Закэшированные tool_id после синхронизации",
    )
    last_sync_at: datetime | None = DbField(default=None)
    description: str | None = DbField(default=None, description="Описание сервера")
    source: MCPServerSource = DbField(default=MCPServerSource.MANUAL)
    catalog_id: str | None = DbField(default=None)
    catalog_snapshot_hash: str | None = DbField(default=None)
    catalog_auto_provisioned: bool = DbField(default=False)
    override_locked: bool = DbField(default=False)
    override_locked_at: datetime | None = DbField(default=None)
    override_locked_by_user_id: str | None = DbField(default=None)
    # Вычисляется при ответе API. db_reverse_fk не создаёт колонку.
    icon_url: str | None = DbField(default=None, db_reverse_fk="mcp_server_id")

    @field_validator("transport_type", mode="before")
    @classmethod
    def parse_transport_type(cls, value: str | MCPTransportType) -> MCPTransportType:
        return MCPTransportType(value)

    @classmethod
    def row_id(cls, server_id: str) -> str:
        company_id = require_active_company().company_id
        if server_id == "" or company_id == "":
            raise ValueError("server_id is required")
        if ":" in server_id or ":" in company_id:
            raise ValueError("server_id and company_id must not contain ':'")
        return f"{company_id}:{server_id}"

    @model_validator(mode="after")
    def bind_company(self) -> Self:
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        expected = type(self).row_id(self.server_id)
        if self.mcp_server_id == "":
            self.mcp_server_id = expected
        elif self.mcp_server_id != expected:
            raise ValueError("mcp_server_id does not match company_id and server_id")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        expected = type(self).row_id(self.server_id)
        if self.company_id == "" or self.mcp_server_id != expected:
            raise ValueError("mcp_server_id does not match the active company")


class MCPCallResult(BaseModel):
    """Результат вызова MCP tool."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)

    is_error: bool = Field(default=False, alias="isError", description="Флаг ошибки")
    content: list[JsonObject] = Field(
        default_factory=list,
        description="Контент ответа (text, image, etc)"
    )
    structured_content: JsonObject | None = Field(
        default=None,
        alias="structuredContent",
        description="Structured tool result from MCP 2025-11-25",
    )
    meta: JsonObject | None = Field(
        default=None,
        alias="_meta",
        description="MCP result metadata",
    )

    def get_text(self) -> str:
        """Извлекает текстовый контент из результата."""
        texts: list[str] = []
        for item in self.content:
            if item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join(texts)


class MCPServerListPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    search: str = ""
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class MCPServerIdPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    server_id: str = Field(..., min_length=2, max_length=64)


class MCPServerUpdateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str | None = None
    url: str | None = None
    transport_type: MCPTransportType | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None
    description: str | None = None


class MCPServerUpdatePayload(MCPServerUpdateRequest):
    server_id: str = Field(..., min_length=2, max_length=64)


class MCPServerDeletedResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    status: Literal["deleted"]
    server_id: str


class MCPSyncResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    success: bool
    tools_count: int
    tools: list[MCPDiscoveredTool]


class MCPTestResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    success: bool
    message: str
    tools_count: int
    transport_type: MCPTransportType
    url: str
