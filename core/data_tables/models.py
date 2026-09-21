"""Канонические модели DataTable (SQLite FileRecord). Публичный id = file_id."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from core.documents.viewer.models import (
    DataTableColumnSnapshot,
    DataTableColumnType,
    DataTableSchemaSnapshot,
    DataTableTableSnapshot,
    DataTableViewerScope,
)
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

DATA_TABLE_CONTENT_TYPE = "application/vnd.sqlite3"
DATA_TABLE_EXTENSION = ".sqlite"
DATA_TABLE_SCHEMA_VERSION = 1
PLATFORM_META_TABLE = "_platform_meta"
PLATFORM_COLUMNS_TABLE = "_platform_columns"
SYSTEM_COLUMNS: frozenset[str] = frozenset({"row_id", "created_at", "updated_at"})
MAX_PAGE_LIMIT = 200
MAX_SEARCH_Q_LENGTH = 200
MAX_EXPORT_ROWS = 100_000

DataTableScope = DataTableViewerScope
DataTableCellValue = str | int | float | bool | None


def normalize_data_table_filename(original_name: str) -> str:
    path = Path(original_name)
    stem = path.stem.strip()
    if stem == "":
        raise ValueError("original_name stem is required")
    suffix = path.suffix.lower()
    if suffix in {".db", DATA_TABLE_EXTENSION, ""}:
        return f"{stem}{DATA_TABLE_EXTENSION}"
    raise ValueError(
        f"DataTable filename must use {DATA_TABLE_EXTENSION} (got {original_name!r})"
    )


class DataTableColumnSpec(StrictBaseModel):
    name: str
    column_type: DataTableColumnType
    not_null: bool = False


class DataTableCreateTableRequest(StrictBaseModel):
    name: str
    columns: list[DataTableColumnSpec]


class DataTableCreateRequest(StrictBaseModel):
    original_name: str
    scope: DataTableScope
    flow_id: str | None = None
    session_id: str | None = None
    namespace: str | None = None
    tables: list[DataTableCreateTableRequest] = Field(default_factory=list)


class DataTableAddColumnRequest(StrictBaseModel):
    name: str
    column_type: DataTableColumnType
    not_null: bool = False


class DataTableInsertRowsRequest(StrictBaseModel):
    rows: list[JsonObject]


class DataTableUpdateRowRequest(StrictBaseModel):
    values: JsonObject


class DataTableQueryRequest(StrictBaseModel):
    sql: str


class DataTableImportRequest(StrictBaseModel):
    """Импорт таблицы из CSV/XLSX, уже загруженного через chunked Files API."""

    table_name: str = Field(min_length=1)
    source_format: Literal["csv", "xlsx"]
    upload_file_id: str = Field(min_length=1)


class DataTableDeleteRowsRequest(StrictBaseModel):
    row_ids: list[int] = Field(min_length=1)


class DataTablePromoteRequest(StrictBaseModel):
    flow_id: str
    original_name: str | None = None


class DataTableRow(StrictBaseModel):
    row_id: int
    created_at: str
    updated_at: str
    values: JsonObject


class DataTableFileSnapshot(StrictBaseModel):
    file_id: str
    original_name: str
    content_type: str
    file_size: int
    checksum: str | None = None
    schema_snapshot: DataTableSchemaSnapshot


class DataTableQueryResult(StrictBaseModel):
    columns: list[str]
    rows: list[list[JsonValue]]
    row_count: int = Field(ge=0)


class DataTableInsertRowsResponse(StrictBaseModel):
    row_ids: list[int]


class DataTableUpdateRowResponse(StrictBaseModel):
    status: Literal["updated"] = "updated"


class DataTableDeleteRowsResponse(StrictBaseModel):
    deleted: int = Field(ge=0)


__all__ = [
    "DATA_TABLE_CONTENT_TYPE",
    "DATA_TABLE_EXTENSION",
    "DATA_TABLE_SCHEMA_VERSION",
    "MAX_PAGE_LIMIT",
    "PLATFORM_COLUMNS_TABLE",
    "PLATFORM_META_TABLE",
    "SYSTEM_COLUMNS",
    "DataTableAddColumnRequest",
    "DataTableCellValue",
    "DataTableColumnSnapshot",
    "DataTableColumnSpec",
    "DataTableColumnType",
    "DataTableCreateRequest",
    "DataTableCreateTableRequest",
    "DataTableDeleteRowsRequest",
    "DataTableDeleteRowsResponse",
    "DataTableFileSnapshot",
    "DataTableImportRequest",
    "DataTableInsertRowsRequest",
    "DataTableInsertRowsResponse",
    "DataTablePromoteRequest",
    "DataTableQueryRequest",
    "DataTableQueryResult",
    "DataTableRow",
    "DataTableSchemaSnapshot",
    "DataTableScope",
    "DataTableTableSnapshot",
    "DataTableUpdateRowRequest",
    "DataTableUpdateRowResponse",
]
