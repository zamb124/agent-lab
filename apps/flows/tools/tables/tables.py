"""Builtin tools: platform DataTable SQLite files (file_id)."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.files.state_file_refs import upsert_state_file
from apps.flows.src.state import ExecutionState
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.data_table_client import DataTableClient
from core.data_tables.models import (
    DataTableAddColumnRequest,
    DataTableColumnSpec,
    DataTableCreateTableRequest,
    DataTableSchemaSnapshot,
)
from core.files.file_ref import FileRef
from core.types import JsonObject, require_json_object

_TAGS = ["tables"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)
DataTableScopeArg = Literal["flow_asset", "flow_session"]


class TablesCreateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(
        description="Human-readable DataTable name; base of the .sqlite filename when original_name is not set",
    )
    columns: list[DataTableColumnSpec] = Field(description="Column definitions of the first table")
    scope: DataTableScopeArg = Field(
        "flow_session",
        description="flow_session — lives with the session TTL; flow_asset — permanent file under Flows/{flow}",
    )
    table_name: str = Field("data", description="Name of the first SQL table to create")
    original_name: str | None = Field(
        None,
        description="Explicit .sqlite filename; defaults to {name}.sqlite",
    )


class TablesFileIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")


class TablesSchemaArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")
    table_name: str | None = Field(None, description="Table to create; omit to only read the schema")
    columns: list[DataTableColumnSpec] | None = Field(
        None,
        description="Column definitions; a single-item list on an existing table adds one column",
    )


class TablesQueryArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")
    sql: str = Field(
        description=(
            "One SELECT/INSERT/UPDATE/DELETE statement; "
            "DDL, ATTACH, PRAGMA and multiple statements are forbidden"
        ),
    )


class TablesInsertArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")
    table_name: str = Field(description="Target table name")
    rows: list[JsonObject] = Field(description="Rows as JSON objects keyed by column name")


class TablesUpdateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")
    table_name: str = Field(description="Target table name")
    row_id: int = Field(description="row_id of the row to update")
    values: JsonObject = Field(description="Column name → new value map")


class TablesDeleteRowsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    file_id: str = Field(description="file_id of the DataTable (.sqlite) file")
    table_name: str = Field(description="Target table name")
    row_ids: list[int] = Field(min_length=1, description="row_id values to delete")


def _dump(payload: BaseModel, label: str) -> JsonObject:
    return require_json_object(payload.model_dump(mode="json"), label)


def _client() -> DataTableClient:
    return DataTableClient()


@tool(
    name="tables_create",
    description=(
        "Creates a platform DataTable SQLite file (Documents) and a first named table. "
        "scope=flow_session lives with the session TTL; flow_asset is permanent under Flows/{flow}. "
        "Returns file_id. Use tables_insert / tables_query afterwards."
    ),
    tags=_TAGS,
    parameters_model=TablesCreateArgs,
    permission=_PERM,
)
async def tables_create(
    name: str,
    columns: list[DataTableColumnSpec],
    state: ExecutionState,
    scope: DataTableScopeArg = "flow_session",
    table_name: str = "data",
    original_name: str | None = None,
) -> JsonObject:
    flow_id = state.session_flow_id
    filename = original_name if original_name is not None else f"{name}.sqlite"
    record = await _client().create(
        original_name=filename,
        scope=scope,
        flow_id=flow_id,
        session_id=state.session_id if scope == "flow_session" else None,
        tables=[DataTableCreateTableRequest(name=table_name, columns=columns)],
    )
    file_ref = FileRef.model_validate(record)
    upsert_state_file(state, file_ref)
    snapshot = await _client().snapshot(record.file_id)
    return require_json_object(
        {
            "file_id": record.file_id,
            "original_name": record.original_name,
            "scope": snapshot.schema_snapshot.scope,
            "schema": snapshot.schema_snapshot.model_dump(mode="json"),
        },
        "tables_create.result",
    )


@tool(
    name="tables_list",
    description="Lists named SQL tables inside a DataTable file_id (schema snapshot, not row dump).",
    tags=_TAGS,
    parameters_model=TablesFileIdArgs,
    permission=_PERM,
)
async def tables_list(file_id: str, state: ExecutionState) -> JsonObject:
    _ = state
    snapshot = await _client().snapshot(file_id)
    return _dump(snapshot, "tables_list.result")


@tool(
    name="tables_schema",
    description=(
        "Reads schema of a DataTable file_id, or adds a table (table_name + columns) "
        "or a column when columns is a single-item list and the table already exists."
    ),
    tags=_TAGS,
    parameters_model=TablesSchemaArgs,
    permission=_PERM,
)
async def tables_schema(
    file_id: str,
    state: ExecutionState,
    table_name: str | None = None,
    columns: list[DataTableColumnSpec] | None = None,
) -> JsonObject:
    _ = state
    client = _client()
    if table_name is None:
        snapshot = await client.get_schema(file_id)
        return _dump(snapshot, "tables_schema.result")
    if columns is None or len(columns) == 0:
        snapshot = await client.get_schema(file_id)
        return _dump(snapshot, "tables_schema.result")
    existing: DataTableSchemaSnapshot = await client.get_schema(file_id)
    names = {table.name for table in existing.tables}
    if table_name in names and len(columns) == 1:
        snapshot = await client.add_column(
            file_id,
            table_name,
            DataTableAddColumnRequest(
                name=columns[0].name,
                column_type=columns[0].column_type,
                not_null=columns[0].not_null,
            ),
        )
        return _dump(snapshot, "tables_schema.add_column")
    snapshot = await client.create_table(
        file_id,
        DataTableCreateTableRequest(name=table_name, columns=columns),
    )
    return _dump(snapshot, "tables_schema.create_table")


@tool(
    name="tables_query",
    description=(
        "Runs one SELECT/INSERT/UPDATE/DELETE against user tables of a DataTable file_id. "
        "DDL, ATTACH, PRAGMA and multiple statements are forbidden."
    ),
    tags=_TAGS,
    parameters_model=TablesQueryArgs,
    permission=_PERM,
)
async def tables_query(file_id: str, sql: str, state: ExecutionState) -> JsonObject:
    _ = state
    result = await _client().query(file_id, sql)
    return _dump(result, "tables_query.result")


@tool(
    name="tables_insert",
    description="Inserts rows into a named table of a DataTable file_id. Returns new row_id values.",
    tags=_TAGS,
    parameters_model=TablesInsertArgs,
    permission=_PERM,
)
async def tables_insert(
    file_id: str,
    table_name: str,
    rows: list[JsonObject],
    state: ExecutionState,
) -> JsonObject:
    _ = state
    row_ids = await _client().insert_rows(file_id, table_name, rows)
    return require_json_object({"row_ids": row_ids}, "tables_insert.result")


@tool(
    name="tables_update",
    description="Updates one row of a DataTable by row_id.",
    tags=_TAGS,
    parameters_model=TablesUpdateArgs,
    permission=_PERM,
)
async def tables_update(
    file_id: str,
    table_name: str,
    row_id: int,
    values: JsonObject,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    await _client().update_row(file_id, table_name, row_id, values)
    return require_json_object({"status": "updated"}, "tables_update.result")


@tool(
    name="tables_delete_rows",
    description="Deletes rows by row_id from a named table of a DataTable file_id.",
    tags=_TAGS,
    parameters_model=TablesDeleteRowsArgs,
    permission=_PERM,
)
async def tables_delete_rows(
    file_id: str,
    table_name: str,
    row_ids: list[int],
    state: ExecutionState,
) -> JsonObject:
    _ = state
    deleted = await _client().delete_rows(file_id, table_name, row_ids)
    return require_json_object({"deleted": deleted}, "tables_delete_rows.result")


TABLES_TOOLS = (
    tables_create,
    tables_list,
    tables_schema,
    tables_query,
    tables_insert,
    tables_update,
    tables_delete_rows,
)
