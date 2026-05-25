"""
Модель ToolReference - инструмент с inline кодом или MCP.
"""

from __future__ import annotations

import copy
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.types import JsonObject, JsonValue, require_json_object

from .enums import CodeMode, ReactToolRole

Permission = str | list[str] | None


class ToolReference(BaseModel):
    """Инструмент с inline кодом"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "tool"},
        extra="forbid",
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
        object.__setattr__(self, "name", label)
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

    def effective_parameters_schema(self) -> JsonObject:
        """Canonical JSON Schema параметров для LLM."""
        if self.parameters_schema is None:
            raise ValueError(f"ToolReference '{self.tool_id}' requires parameters_schema")
        schema = require_json_object(
            copy.deepcopy(self.parameters_schema),
            f"tool.{self.tool_id}.parameters_schema",
        )
        if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            raise ValueError(
                f"ToolReference '{self.tool_id}' parameters_schema must be object JSON Schema"
            )
        return schema

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
