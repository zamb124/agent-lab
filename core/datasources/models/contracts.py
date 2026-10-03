"""Контракты datasource без таблиц."""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    Field,
)

from core.models.base import StrictBaseModel
from core.types import JsonObject


def datasource_required(value: str, field_name: str) -> str:
    if value.strip() == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value


class DatasourceExecutorKind(StrEnum):
    PLATFORM = "platform"
    MCP = "mcp"
    FLOW = "flow"

class DatasourceOperation(StrEnum):
    INTROSPECT = "introspect"
    QUERY = "query"
    EXECUTE = "execute"

class DatasourceSqlOperation(StrEnum):
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"

class DatasourceSslMode(StrEnum):
    DISABLE = "disable"
    REQUIRE = "require"
    VERIFY_FULL = "verify-full"

class DatasourceColumn(StrictBaseModel):
    name: str
    data_type: str

class DatasourceTable(StrictBaseModel):
    table_name: str
    columns: list[DatasourceColumn] = Field(default_factory=list)

class DatasourceSchemaSnapshot(StrictBaseModel):
    tables: list[DatasourceTable] = Field(default_factory=list)

class DatasourceQueryResult(StrictBaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[JsonObject] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    truncated: bool = False

class DatasourceExecuteResult(StrictBaseModel):
    rowcount: int = Field(ge=0)

class DatasourceTestResult(StrictBaseModel):
    ok: bool
    latency_ms: int = Field(ge=0)
    server_version: str | None = None

class DatasourceConnectionCreate(StrictBaseModel):
    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_mode: DatasourceSslMode = DatasourceSslMode.REQUIRE
    allowed_operations: list[DatasourceSqlOperation] = Field(
        default_factory=lambda: [DatasourceSqlOperation.SELECT]
    )
    statement_timeout_ms: int = Field(default=15_000, ge=1, le=120_000)
    max_rows: int = Field(default=1_000, ge=1, le=10_000)
    mcp_server_id: str | None = None
    flow_id: str | None = None
    flow_branch_id: str = "default"

class DatasourceConnectionPatch(StrictBaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_mode: DatasourceSslMode | None = None
    allowed_operations: list[DatasourceSqlOperation] | None = None
    statement_timeout_ms: int | None = Field(default=None, ge=1, le=120_000)
    max_rows: int | None = Field(default=None, ge=1, le=10_000)
    mcp_server_id: str | None = None
    flow_id: str | None = None
    flow_branch_id: str | None = None

class DatasourceConnectionPatchPayload(DatasourceConnectionPatch):
    datasource_id: str = Field(min_length=1)

class DatasourceListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class DatasourceConnectorUpsert(StrictBaseModel):
    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    executor: DatasourceExecutorKind
    icon: str = "database"
    credential_schema: JsonObject
    operations: list[DatasourceOperation] = Field(min_length=1)
    mcp_server_id: str | None = None
    mcp_introspect_tool: str | None = None
    mcp_query_tool: str | None = None
    mcp_execute_tool: str | None = None
    flow_id: str | None = None
    flow_branch_id: str = "default"

class DatasourceSchemaArgs(StrictBaseModel):
    datasource_id: str = Field(min_length=1, description="Company datasource_id to introspect")

class DatasourceSqlRequest(StrictBaseModel):
    sql: str = Field(min_length=1, description="Single SQL statement with named :param placeholders")
    params: JsonObject = Field(
        default_factory=dict,
        description="Named parameters bound to :param placeholders in sql",
    )

class DatasourceSqlCallArgs(DatasourceSqlRequest):
    datasource_id: str = Field(min_length=1, description="Company datasource_id to run the statement on")

DatasourceProtocolResult = (
    DatasourceSchemaSnapshot | DatasourceQueryResult | DatasourceExecuteResult | DatasourceTestResult
)

