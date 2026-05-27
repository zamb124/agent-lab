"""
Модель ToolReference - инструмент с inline кодом или MCP.
"""

from __future__ import annotations

import copy
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.integrations.mcp import (
    MCPDiscoveredTool,
    mcp_parameters_schema_hash,
    mcp_tool_reference_id,
    validate_mcp_output_schema,
    validate_mcp_parameters_schema,
)
from core.types import JsonObject, JsonValue, require_json_object

from .enums import CodeMode, ReactToolRole


class ToolReference(BaseModel):
    """Инструмент с inline кодом"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "tool"},
        extra="forbid",
        use_enum_values=False,
    )

    tool_id: str = Field(..., description="ID инструмента")
    name: str | None = Field(
        default=None,
        description="Подпись в UI (flows editor, модалки). Если не задана — title или tool_id.",
    )
    title: str | None = Field(default=None, description="Название для отображения")
    description: str | None = Field(default=None, description="Описание инструмента")
    parameters_schema: JsonObject | None = Field(
        default=None,
        description=(
            "Полная JSON Schema объекта параметров для LLM "
            "(type: object, properties, required, minLength, default, items и т.д.)."
        ),
    )
    params: JsonObject = Field(default_factory=dict, description="Параметры инструмента")
    resources: JsonObject = Field(
        default_factory=dict,
        description="Декларативные ресурсы tool для runtime-политик",
    )
    language: str = Field(default="python", description="Язык исполнения code tool")
    entrypoint: str | None = Field(
        default=None,
        description="Имя entrypoint-функции code tool; None = первая функция в source",
    )
    code: str | None = Field(default=None, description="Код инструмента")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом к tool. Пустой список = доступ для всех",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def convert_none_to_list(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return []
        return v

    @model_validator(mode="after")
    def default_display_name(self) -> Self:
        raw = (self.name or "").strip()
        if raw:
            return self
        t = (self.title or "").strip()
        label = t if t else self.tool_id.strip()
        if not label:
            raise ValueError("tool_id must be non-empty for display name")
        self.name = label
        return self

    tags: list[str] = Field(
        default_factory=list,
        description="Группы/категории тула: misc, math, docs, api, validation",
    )
    react_role: ReactToolRole = Field(
        default=ReactToolRole.STANDARD,
        description="Роль в ReAct: standard, reason, exit",
    )
    public_fields: list[str] | None = Field(
        default=None, description="Поля доступные для редактирования в UI. None = все поля доступны"
    )

    # MCP-специфичные поля
    code_mode: CodeMode = Field(
        default=CodeMode.INLINE_CODE, description="Режим кода: inline_code или mcp_tool"
    )
    mcp_server_id: str | None = Field(default=None, description="ID MCP сервера (для MCP тулов)")
    mcp_tool_name: str | None = Field(default=None, description="Имя tool на MCP сервере")
    mcp_schema_hash: str | None = Field(default=None, min_length=64, max_length=64)
    mcp_schema_version: str | None = Field(default=None, min_length=1)
    mcp_output_schema: JsonObject | None = None
    mcp_annotations: JsonObject | None = None
    mcp_execution: JsonObject | None = None

    def effective_parameters_schema(self) -> JsonObject:
        """Canonical JSON Schema параметров для LLM."""
        if self.parameters_schema is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires parameters_schema")
        schema = require_json_object(
            copy.deepcopy(self.parameters_schema),
            f"tool.{self.tool_id}.parameters_schema",
        )
        if self.code_mode == CodeMode.MCP_TOOL:
            return validate_mcp_parameters_schema(
                schema,
                f"ToolReference '{self.tool_id}'",
            )
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            raise ValueError(
                f"ToolReference '{self.tool_id}' parameters_schema must be object JSON Schema"
            )
        return schema

    def require_mcp_contract(self) -> MCPDiscoveredTool:
        if self.code_mode != CodeMode.MCP_TOOL:
            raise ValueError(f"ToolReference '{self.tool_id}' is not an MCP tool")

        raw_server_id = self.mcp_server_id
        if raw_server_id is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_server_id")
        server_id = raw_server_id.strip()
        if not server_id:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_server_id")

        raw_tool_name = self.mcp_tool_name
        if raw_tool_name is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_tool_name")
        tool_name = raw_tool_name.strip()
        if not tool_name:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_tool_name")

        expected_tool_id = mcp_tool_reference_id(server_id, tool_name)
        if self.tool_id != expected_tool_id:
            raise ValueError(
                f"ToolReference '{self.tool_id}' MCP ids must match {expected_tool_id!r}"
            )

        schema_hash = self.mcp_schema_hash
        if schema_hash is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_schema_hash")

        raw_schema_version = self.mcp_schema_version
        if raw_schema_version is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_schema_version")
        schema_version = raw_schema_version.strip()
        if not schema_version:
            raise ValueError(f"ToolReference '{self.tool_id}' requires mcp_schema_version")

        parameters_schema = self.effective_parameters_schema()
        expected_hash = mcp_parameters_schema_hash(parameters_schema)
        if schema_hash != expected_hash:
            raise ValueError(
                f"ToolReference '{self.tool_id}' mcp_schema_hash does not match parameters_schema"
            )

        output_schema = (
            validate_mcp_output_schema(
                self.mcp_output_schema,
                f"ToolReference '{self.tool_id}'",
            )
            if self.mcp_output_schema is not None
            else None
        )

        return MCPDiscoveredTool(
            server_id=server_id,
            tool_name=tool_name,
            title=self.title,
            description=self.description,
            icons=None,
            parameters_schema=parameters_schema,
            output_schema=output_schema,
            execution=self.mcp_execution,
            annotations=self.mcp_annotations,
            meta=None,
            schema_hash=schema_hash,
            schema_version=schema_version,
        )

    @model_validator(mode="after")
    def validate_mcp_contract(self) -> Self:
        if self.code_mode != CodeMode.MCP_TOOL:
            return self
        _ = self.require_mcp_contract()
        return self

    def to_registry_format(self) -> JsonObject:
        """Преобразует в формат registry API."""
        attrs: JsonObject = {
            "description": self.description or "",
            "parameters_schema": self.effective_parameters_schema(),
        }
        return {
            "name": self.tool_id,
            "type": "inline_code",
            "attributes": attrs,
        }
