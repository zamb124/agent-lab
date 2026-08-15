"""DataTable SDK capabilities: definitions + DataTableService invoke."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, Field, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.data_tables.models import (
    DataTableAddColumnRequest,
    DataTableColumnSpec,
    DataTableColumnType,
    DataTableCreateTableRequest,
    DataTableScope,
)
from core.data_tables.service import DataTableService
from core.types import JsonObject, JsonValue, require_json_object

TablesArgsModel: TypeAlias = type[BaseModel]

_TABLES_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "JSON from DataTableService (file_id / schema / rows, no HTTP envelope).",
}


class TablesCreateArgs(BaseModel):
    original_name: str
    scope: DataTableScope
    flow_id: str | None = None
    session_id: str | None = None
    namespace: str | None = None
    tables: list[DataTableCreateTableRequest] = Field(default_factory=list)


class TablesFileIdArgs(BaseModel):
    file_id: str


class TablesCreateTableArgs(BaseModel):
    file_id: str
    name: str
    columns: list[DataTableColumnSpec]


class TablesAddColumnArgs(BaseModel):
    file_id: str
    table_name: str
    name: str
    column_type: DataTableColumnType
    not_null: bool = False


class TablesQueryArgs(BaseModel):
    file_id: str
    sql: str


class TablesInsertArgs(BaseModel):
    file_id: str
    table_name: str
    rows: list[JsonObject]


class TablesUpdateArgs(BaseModel):
    file_id: str
    table_name: str
    row_id: int
    values: JsonObject


class TablesDeleteRowsArgs(BaseModel):
    file_id: str
    table_name: str
    row_ids: list[int] = Field(min_length=1)


def _input_schema(model: TablesArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: TablesArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"tables.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_TABLES_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["tables"],
        sdk_namespace="tables",
        sdk_method=method,
    )


TABLES_CAPABILITY_SPECS: tuple[tuple[str, str, str, TablesArgsModel], ...] = (
    (
        "create",
        "Create DataTable file",
        "Creates a SQLite DataTable FileRecord. scope is flow_asset, flow_session or office_document.",
        TablesCreateArgs,
    ),
    (
        "list",
        "List DataTable schema",
        "Returns schema snapshot (tables, columns, row counts) for file_id.",
        TablesFileIdArgs,
    ),
    (
        "schema",
        "Get DataTable schema",
        "Returns schema snapshot for file_id.",
        TablesFileIdArgs,
    ),
    (
        "create_table",
        "Create table inside DataTable",
        "Adds a named SQL table with typed columns.",
        TablesCreateTableArgs,
    ),
    (
        "add_column",
        "Add DataTable column",
        "Adds a typed column to an existing table.",
        TablesAddColumnArgs,
    ),
    (
        "query",
        "Query DataTable SQL",
        "Runs one SELECT/INSERT/UPDATE/DELETE. DDL/ATTACH/PRAGMA are forbidden.",
        TablesQueryArgs,
    ),
    (
        "insert",
        "Insert DataTable rows",
        "Inserts rows into a named table. Returns row_ids.",
        TablesInsertArgs,
    ),
    (
        "update",
        "Update DataTable row",
        "Patches one row by row_id.",
        TablesUpdateArgs,
    ),
    (
        "delete_rows",
        "Delete DataTable rows",
        "Deletes rows by row_id.",
        TablesDeleteRowsArgs,
    ),
)


def tables_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"tables.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in TABLES_CAPABILITY_SPECS
    }


def _dump(payload: BaseModel, label: str) -> JsonObject:
    return require_json_object(payload.model_dump(mode="json"), label)


async def invoke_tables_client(
    method: str,
    kwargs: JsonObject,
    service: DataTableService,
) -> JsonValue:
    specs = {item[0]: item[3] for item in TABLES_CAPABILITY_SPECS}
    args_model = specs.get(method)
    if args_model is None:
        raise ValueError(f"unknown tables method {method!r}")
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if method == "create" and isinstance(args, TablesCreateArgs):
        record = await service.create(
            original_name=args.original_name,
            scope=args.scope,
            flow_id=args.flow_id,
            session_id=args.session_id,
            tables=args.tables,
            namespace=args.namespace,
        )
        return _dump(record, "tables.create")
    if method in {"list", "schema"} and isinstance(args, TablesFileIdArgs):
        snapshot = await service.snapshot(args.file_id)
        return _dump(snapshot, f"tables.{method}")
    if method == "create_table" and isinstance(args, TablesCreateTableArgs):
        snapshot = await service.create_table(
            args.file_id,
            DataTableCreateTableRequest(name=args.name, columns=args.columns),
        )
        return _dump(snapshot, "tables.create_table")
    if method == "add_column" and isinstance(args, TablesAddColumnArgs):
        snapshot = await service.add_column(
            args.file_id,
            args.table_name,
            DataTableAddColumnRequest(
                name=args.name,
                column_type=args.column_type,
                not_null=args.not_null,
            ),
        )
        return _dump(snapshot, "tables.add_column")
    if method == "query" and isinstance(args, TablesQueryArgs):
        result = await service.query(args.file_id, args.sql)
        return _dump(result, "tables.query")
    if method == "insert" and isinstance(args, TablesInsertArgs):
        row_ids = await service.insert_rows(args.file_id, args.table_name, args.rows)
        return require_json_object({"row_ids": row_ids}, "tables.insert")
    if method == "update" and isinstance(args, TablesUpdateArgs):
        await service.update_row(args.file_id, args.table_name, args.row_id, args.values)
        return require_json_object({"status": "updated"}, "tables.update")
    if method == "delete_rows" and isinstance(args, TablesDeleteRowsArgs):
        deleted = await service.delete_rows(args.file_id, args.table_name, args.row_ids)
        return require_json_object({"deleted": deleted}, "tables.delete_rows")
    raise ValueError(f"tables.{method} args mismatch")
