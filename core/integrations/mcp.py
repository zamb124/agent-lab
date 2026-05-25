"""Платформенные контракты MCP (Model Context Protocol)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from core.types import JsonObject


class MCPToolInfo(BaseModel):
    """Описание одного MCP-tool в ответе MCP-сервера на ``tools/list``.

    Внутреннее имя поля — ``input_schema`` (snake_case по glossary).
    Внешний JSON-RPC по спецификации MCP использует camelCase
    ``inputSchema`` — это единственная причина alias: external spec, не
    backward-compatibility.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(..., description="Имя tool на MCP сервере")
    description: str | None = Field(
        default=None,
        description="Человекочитаемое описание tool",
    )
    input_schema: JsonObject | None = Field(
        default=None,
        validation_alias=AliasChoices("input_schema", "inputSchema"),
        serialization_alias="inputSchema",
        description="JSON Schema параметров tool",
    )


__all__ = ["MCPToolInfo"]
