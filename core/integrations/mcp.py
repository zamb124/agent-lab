"""Strict platform contracts for Model Context Protocol tool discovery."""

from __future__ import annotations

import hashlib
import json
from typing import ClassVar, Self

from pydantic import ConfigDict, Field, model_validator

from core.models import StrictBaseModel
from core.types import JsonObject

MCP_PROTOCOL_VERSION = "2025-11-25"


def mcp_tool_reference_id(server_id: str, tool_name: str) -> str:
    sid = server_id.strip()
    tname = tool_name.strip()
    if not sid:
        raise ValueError("server_id is required")
    if not tname:
        raise ValueError("tool_name is required")
    return f"mcp:{sid}:{tname}"


def mcp_parameters_schema_hash(parameters_schema: JsonObject) -> str:
    payload = json.dumps(
        parameters_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_mcp_parameters_schema(parameters_schema: JsonObject, label: str) -> JsonObject:
    if parameters_schema.get("type") != "object":
        raise ValueError(f"{label}: parameters_schema.type must be 'object'")
    properties = parameters_schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError(f"{label}: parameters_schema.properties must be an object")
    return parameters_schema


def validate_mcp_output_schema(output_schema: JsonObject, label: str) -> JsonObject:
    if output_schema.get("type") != "object":
        raise ValueError(f"{label}: output_schema.type must be 'object'")
    properties = output_schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError(f"{label}: output_schema.properties must be an object")
    return output_schema


class MCPInitializeResult(StrictBaseModel):
    """Strict initialize result for MCP protocol 2025-11-25."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
        populate_by_name=True,
    )

    protocol_version: str = Field(
        ...,
        min_length=1,
        validation_alias="protocolVersion",
        serialization_alias="protocolVersion",
    )
    capabilities: JsonObject
    server_info: JsonObject = Field(
        ...,
        validation_alias="serverInfo",
        serialization_alias="serverInfo",
    )
    instructions: str | None = Field(default=None, min_length=1)
    meta: JsonObject | None = Field(
        default=None,
        validation_alias="_meta",
        serialization_alias="_meta",
    )

    @model_validator(mode="after")
    def validate_protocol_version(self) -> Self:
        if self.protocol_version != MCP_PROTOCOL_VERSION:
            raise ValueError(
                "MCP initialize protocolVersion mismatch: "
                + f"expected {MCP_PROTOCOL_VERSION!r}, got {self.protocol_version!r}"
            )
        return self


class MCPToolDefinition(StrictBaseModel):
    """MCP wire tool definition.

    Python code uses ``parameters_schema``. JSON-RPC MCP uses ``inputSchema`` on
    the wire, and that alias is accepted only through ``from_wire``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
        populate_by_name=True,
    )

    name: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    icons: list[JsonObject] | None = None
    parameters_schema: JsonObject = Field(
        ...,
        validation_alias="inputSchema",
        serialization_alias="inputSchema",
    )
    output_schema: JsonObject | None = Field(
        default=None,
        validation_alias="outputSchema",
        serialization_alias="outputSchema",
    )
    execution: JsonObject | None = None
    annotations: JsonObject | None = None
    meta: JsonObject | None = Field(
        default=None,
        validation_alias="_meta",
        serialization_alias="_meta",
    )

    @model_validator(mode="after")
    def validate_schema(self) -> Self:
        _ = validate_mcp_parameters_schema(
            self.parameters_schema,
            f"MCP tool {self.name!r}",
        )
        if self.output_schema is not None:
            _ = validate_mcp_output_schema(
                self.output_schema,
                f"MCP tool {self.name!r}",
            )
        return self

    @classmethod
    def from_wire(cls, payload: JsonObject) -> "MCPToolDefinition":
        if "inputSchema" not in payload:
            raise ValueError("MCP tool definition requires inputSchema")
        if (
            "input_schema" in payload
            or "parameters_schema" in payload
            or "output_schema" in payload
            or "schema_hash" in payload
            or "schema_version" in payload
        ):
            raise ValueError("MCP wire tool definition must use MCP camelCase fields only")
        return cls.model_validate(payload)

    def to_discovered(
        self,
        *,
        server_id: str,
        schema_version: str,
    ) -> "MCPDiscoveredTool":
        return MCPDiscoveredTool(
            server_id=server_id,
            tool_name=self.name,
            title=self.title,
            description=self.description,
            icons=self.icons,
            parameters_schema=self.parameters_schema,
            output_schema=self.output_schema,
            execution=self.execution,
            annotations=self.annotations,
            meta=self.meta,
            schema_hash=mcp_parameters_schema_hash(self.parameters_schema),
            schema_version=schema_version,
        )


class MCPDiscoveredTool(StrictBaseModel):
    """Internal platform contract for a discovered MCP tool."""

    server_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    icons: list[JsonObject] | None = None
    parameters_schema: JsonObject
    output_schema: JsonObject | None = None
    execution: JsonObject | None = None
    annotations: JsonObject | None = None
    meta: JsonObject | None = None
    schema_hash: str = Field(..., min_length=64, max_length=64)
    schema_version: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_schema(self) -> Self:
        _ = validate_mcp_parameters_schema(
            self.parameters_schema,
            f"MCP discovered tool {self.server_id!r}/{self.tool_name!r}",
        )
        if self.output_schema is not None:
            _ = validate_mcp_output_schema(
                self.output_schema,
                f"MCP discovered tool {self.server_id!r}/{self.tool_name!r}",
            )
        expected_hash = mcp_parameters_schema_hash(self.parameters_schema)
        if self.schema_hash != expected_hash:
            raise ValueError(
                "MCP discovered tool schema_hash does not match parameters_schema"
            )
        return self


__all__ = [
    "MCPDiscoveredTool",
    "MCPInitializeResult",
    "MCPToolDefinition",
    "MCP_PROTOCOL_VERSION",
    "mcp_parameters_schema_hash",
    "mcp_tool_reference_id",
    "validate_mcp_output_schema",
    "validate_mcp_parameters_schema",
]
