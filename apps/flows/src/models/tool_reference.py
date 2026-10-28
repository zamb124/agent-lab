"""
Модель ToolReference - инструмент с inline кодом или MCP.
"""

from __future__ import annotations

import copy
from collections.abc import Collection
from enum import Enum
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from oxyde import Q
from pydantic import ConfigDict, Field, field_validator, model_validator

from core.context.context import get_context
from core.integrations.mcp import (
    MCPDiscoveredTool,
    mcp_parameters_schema_hash,
    mcp_tool_reference_id,
    validate_mcp_output_schema,
    validate_mcp_parameters_schema,
)
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject, JsonValue, require_json_object

from .enums import CodeMode, ReactToolRole

ToolIndexMcpFilter = Literal["all", "exclude", "only"]


class ToolReference(CompanyScopedModel):
    """Инструмент компании. Таблица ``tools`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        use_enum_values=False,
    )

    class Meta:
        is_table: bool = True
        table_name: str = "tools"
        unique_together: list[tuple[str, str]] = [("company_id", "tool_id")]

    tool_id: str = DbField(min_length=1, db_index=True, db_type="TEXT", description="ID инструмента")
    company_id: str = DbField(default="", db_index=True)
    tool_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    name: str | None = DbField(
        default=None,
        db_type="TEXT",
        description="Подпись в UI (flows editor, модалки). Если не задана — title или tool_id.",
    )
    title: str | None = DbField(default=None, db_type="TEXT", description="Название для отображения")
    description: str | None = DbField(default=None, db_type="TEXT", description="Описание инструмента")
    parameters_schema: JsonObject | None = DbField(
        db_type="JSONB",
        default=None,
        description=(
            "Полная JSON Schema объекта параметров для LLM "
            "(type object, properties, required, minLength, default, items и т.д.)."
        ),
    )
    params: JsonObject = DbField(default_factory=dict, db_type="JSONB", description="Параметры инструмента")
    resources: JsonObject = DbField(
        db_type="JSONB",
        default_factory=dict,
        description="Декларативные ресурсы tool для runtime-политик",
    )
    language: str = DbField(default="python", db_type="TEXT", description="Язык исполнения code tool")
    entrypoint: str | None = DbField(
        db_type="TEXT",
        default=None,
        description="Имя entrypoint-функции code tool; None = первая функция в source",
    )
    code: str | None = DbField(default=None, db_type="TEXT", description="Код инструмента")
    permission: list[str] = Field(
        default_factory=list,
        description="Группы с доступом к tool. Пустой список = доступ для всех",
    )
    input_mapping: JsonObject = DbField(
        default_factory=dict,
        db_type="JSONB",
        description=(
            "Маппинг входов при открытии tool как ноды в редакторе / node-as-tool: "
            "target -> @state/@var или JSON-константа"
        ),
    )
    output_mapping: dict[str, str] | None = DbField(
        default=None,
        db_type="JSONB",
        description="Маппинг выходов tool-as-node в state; None = без remapping",
    )
    state_mapping: JsonObject = DbField(
        default_factory=dict,
        db_type="JSONB",
        description="Дополнительный state mapping tool-as-node (MCP/editor)",
    )

    @field_validator("permission", mode="before")
    @classmethod
    def convert_none_to_list(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return []
        return v

    @model_validator(mode="before")
    @classmethod
    def strip_graph_node_type(cls, data: JsonValue) -> JsonValue:
        """UI editor пишет type=code|mcp в tool ref; у ToolReference поля type нет."""
        if not isinstance(data, dict):
            return data
        raw_type = data.get("type")
        if raw_type not in {"code", "mcp"}:
            return data
        return {key: value for key, value in data.items() if key != "type"}

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

    @classmethod
    def row_id_for_active_company(cls, tool_id: str) -> str:
        """Ключ строки из активной компании и tool_id. Нет компании — ValueError. Пустой tool_id или двоеточие в company_id — ValueError."""
        ctx = get_context()
        if ctx is None or ctx.active_company is None or ctx.active_company.company_id == "":
            raise ValueError("tool_id requires an active company")
        company_id = ctx.active_company.company_id
        if tool_id == "" or ":" in company_id:
            raise ValueError("tool_id is required and company_id must not contain ':'")
        return f"{len(company_id)}:{company_id}:{tool_id}"

    @model_validator(mode="after")
    def bind_company(self) -> Self:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            return self
        company_id = ctx.active_company.company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        expected = type(self).row_id_for_active_company(self.tool_id)
        if self.tool_row_id == "":
            self.tool_row_id = expected
        elif self.tool_row_id != expected:
            raise ValueError("tool_row_id does not match company_id and tool_id")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        expected = type(self).row_id_for_active_company(self.tool_id)
        if self.company_id == "" or self.tool_row_id != expected:
            raise ValueError("tool_row_id does not match the active company")
        _ = is_create, update_fields

    @classmethod
    async def list_in_tool_id_order(cls, *, limit: int, offset: int = 0) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        return await cls.objects.order_by("tool_id").limit(limit).offset(offset).all()

    @classmethod
    async def by_tool_ids(cls, tool_ids: list[str]) -> dict[str, Self]:
        if len(tool_ids) == 0:
            return {}
        for tool_id in tool_ids:
            if tool_id == "":
                raise ValueError("tool_id is required")
        rows = await cls.objects.filter(tool_id__in=tool_ids).all()
        found: dict[str, Self] = {}
        for row in rows:
            if row.tool_id in found:
                raise RuntimeError(f"tool_id {row.tool_id} has more than one row in the company")
            found[row.tool_id] = row
        return found

    @classmethod
    def _indexed(
        cls,
        *,
        mcp: ToolIndexMcpFilter,
        exclude_tool_ids: Collection[str] | None,
    ):
        query = cls.objects
        if mcp == "only":
            query = query.filter(_mcp_tools())
        elif mcp == "exclude":
            query = query.filter(~_mcp_tools())
        if exclude_tool_ids:
            query = query.exclude(tool_id__in=list(exclude_tool_ids))
        return query.order_by("tool_id")

    @classmethod
    async def list_tool_index(
        cls,
        *,
        mcp: ToolIndexMcpFilter = "all",
        exclude_tool_ids: Collection[str] | None = None,
    ) -> list[ToolListIndexItem]:
        """Индекс tools, ORDER BY tool_id. Предела нет. mcp=all и пустой exclude_tool_ids не фильтруют."""
        rows = await cls._indexed(mcp=mcp, exclude_tool_ids=exclude_tool_ids).all()
        return [
            ToolListIndexItem(
                tool_id=row.tool_id,
                title=row.title,
                description=row.description,
                tags=list(row.tags),
                code_mode=row.code_mode,
                mcp_server_id=row.mcp_server_id,
            )
            for row in rows
        ]

    @classmethod
    async def count_index(
        cls,
        *,
        mcp: ToolIndexMcpFilter = "all",
        exclude_tool_ids: Collection[str] | None = None,
    ) -> int:
        return await cls._indexed(mcp=mcp, exclude_tool_ids=exclude_tool_ids).count()


def _mcp_tools():
    return (
        Q(code_mode=CodeMode.MCP_TOOL)
        | Q(tool_id__startswith="mcp:")
        | (Q(mcp_server_id__isnull=False) & ~Q(mcp_server_id=""))
    )


class ToolListIndexItem(StrictBaseModel):
    """Проекция списка tools: id и поля фильтра picker без полного ToolReference / code."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    tool_id: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    code_mode: CodeMode = CodeMode.INLINE_CODE
    mcp_server_id: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def tags_none_to_list(cls, value: JsonValue) -> JsonValue:
        if value is None:
            return []
        return value

    @field_validator("code_mode", mode="before")
    @classmethod
    def code_mode_none_to_inline(cls, value: JsonValue) -> JsonValue | CodeMode:
        if value is None or value == "":
            return CodeMode.INLINE_CODE
        return value


class PickerCategory(str, Enum):
    ALL = "all"
    CODE = "code"
    FLOW = "flow"
    MCP = "mcp"


class ToolCreateRequest(StrictBaseModel):
    tool_id: str
    title: str | None = None
    description: str | None = None
    code: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    parameters_schema: JsonObject
    tags: list[str] = Field(default_factory=list)
    react_role: str | None = None
    agent_toolkit_ids: list[str] = Field(default_factory=list)


class ToolResponse(StrictBaseModel):
    tool_id: str
    title: str | None
    description: str | None
    code: str | None = None
    language: str = "python"
    entrypoint: str | None = None
    parameters_schema: JsonObject | None = None
    output_schema: JsonObject | None = None
    effects: list[str] = Field(default_factory=list)
    confirmation_floor: str | None = None
    builtin: bool = False
    tags: list[str] = Field(default_factory=list)
    permission: str | list[str] | None = None
    item_type: str = "tool"
    react_role: str | None = None
    code_mode: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_name: str | None = None
    mcp_schema_hash: str | None = None
    mcp_schema_version: str | None = None
    mcp_output_schema: JsonObject | None = None
    agent_toolkit_ids: list[str] = Field(default_factory=list)


class ToolDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    tool_id: str


class ToolsListPayload(StrictBaseModel):
    limit: int = Field(default=500, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)


class ToolsListAllPayload(StrictBaseModel):
    limit: int = Field(default=20, ge=1, le=20)
    offset: int = Field(default=0, ge=0)
    picker_category: PickerCategory | None = None
    q: str | None = None


class ToolsToolIdPayload(StrictBaseModel):
    tool_id: str = Field(min_length=1)


class ToolsTagGroupsPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
