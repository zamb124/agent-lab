"""
Модели для MCP (Model Context Protocol).

MCP серверы подключаются по HTTP и предоставляют tools для агентов.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MCPTransportType(str, Enum):
    """Тип транспорта MCP сервера."""

    HTTP = "http"
    SSE = "sse"


class MCPServerConfig(BaseModel):
    """
    Конфигурация MCP сервера.

    Хранится в Storage, используется для подключения к внешним MCP серверам.
    Поддерживает @var: ссылки в headers для секретов.

    NOTE: Используем BaseModel вместо StrictBaseModel,
    т.к. StrictBaseModel имеет use_enum_values=True который
    конвертирует enum в строку при присваивании.
    """

    model_config = ConfigDict(extra="forbid")
    server_id: str = Field(..., description="Уникальный идентификатор сервера")
    name: str = Field(..., description="Отображаемое имя сервера")
    url: str = Field(..., description="URL MCP сервера (JSON-RPC endpoint)")
    transport_type: MCPTransportType = Field(
        default=MCPTransportType.HTTP,
        description="Тип транспорта: http или sse"
    )

    @field_validator("transport_type", mode="before")
    @classmethod
    def parse_transport_type(cls, v):
        """Конвертирует строку в enum при десериализации из БД."""
        if isinstance(v, str):
            return MCPTransportType(v)
        return v
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers, поддерживает @var: ссылки"
    )
    is_active: bool = Field(default=True, description="Активен ли сервер")
    cached_tools: list[str] = Field(
        default_factory=list,
        description="Закэшированные tool_id после синхронизации"
    )
    last_sync_at: datetime | None = Field(
        default=None,
        description="Время последней синхронизации"
    )
    description: str | None = Field(default=None, description="Описание сервера")


class MCPToolInfo(BaseModel):
    """
    Информация о tool с MCP сервера.

    Используется при синхронизации для создания ToolReference.
    """

    name: str = Field(..., description="Имя tool на MCP сервере")
    description: str | None = Field(default=None, description="Описание tool")
    input_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema параметров"
    )


class MCPCallResult(BaseModel):
    """Результат вызова MCP tool."""

    is_error: bool = Field(default=False, description="Флаг ошибки")
    content: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Контент ответа (text, image, etc)"
    )

    def get_text(self) -> str:
        """Извлекает текстовый контент из результата."""
        texts = []
        for item in self.content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)
