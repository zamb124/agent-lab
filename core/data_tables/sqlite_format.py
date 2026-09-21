"""SQLite layout и мутации DataTable файла."""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from core.data_tables.identifiers import is_user_table_name, quote_sql_ident, validate_ident
from core.data_tables.models import (
    DATA_TABLE_SCHEMA_VERSION,
    MAX_EXPORT_ROWS,
    MAX_SEARCH_Q_LENGTH,
    PLATFORM_COLUMNS_TABLE,
    PLATFORM_META_TABLE,
    SYSTEM_COLUMNS,
    DataTableColumnSpec,
    DataTableColumnType,
    DataTableRow,
    DataTableSchemaSnapshot,
    DataTableScope,
    DataTableTableSnapshot,
)
from core.documents.viewer.models import DataTableColumnSnapshot
from core.pagination import CursorPage, decode_cursor, encode_cursor
from core.types import JsonObject, JsonValue, parse_json_value
from core.utils.time import utcnow

_SQLITE_TYPE: dict[DataTableColumnType, str] = {
    "text": "TEXT",
    "integer": "INTEGER",
    "real": "REAL",
    "boolean": "INTEGER",
    "datetime": "TEXT",
    "json": "TEXT",
    "file_ref": "TEXT",
}


def _row_get(row: sqlite3.Row, key: str) -> object:
    return cast(object, row[key])


def _row_str(row: sqlite3.Row, key: str) -> str:
    value = _row_get(row, key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str, got {type(value).__name__}")
    return value


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = _row_get(row, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int, got {type(value).__name__}")
    return value


def _execute(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> sqlite3.Cursor:
    return connection.execute(sql, params)


def _sql(*parts: str) -> str:
    return "".join(parts)


def _fetchall(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> list[sqlite3.Row]:
    return list(cast(Sequence[sqlite3.Row], _execute(connection, sql, params).fetchall()))


def _fetchone(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> sqlite3.Row | None:
    return cast(sqlite3.Row | None, _execute(connection, sql, params).fetchone())


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def open_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    _ = _execute(connection, "PRAGMA foreign_keys = ON")
    return connection


def initialize_platform_schema(
    connection: sqlite3.Connection,
    *,
    scope: DataTableScope,
    flow_id: str | None,
    session_id: str | None,
) -> None:
    _ = _execute(
        connection,
        _sql(
            f"CREATE TABLE IF NOT EXISTS {PLATFORM_META_TABLE} ",
            "(key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)",
        ),
    )
    _ = _execute(
        connection,
        _sql(
            f"CREATE TABLE IF NOT EXISTS {PLATFORM_COLUMNS_TABLE} ",
            "(table_name TEXT NOT NULL, column_name TEXT NOT NULL, ",
            "column_type TEXT NOT NULL, position INTEGER NOT NULL, ",
            "not_null INTEGER NOT NULL DEFAULT 0, ",
            "PRIMARY KEY (table_name, column_name))",
        ),
    )
    existing = _meta_map(connection)
    if "schema_version" not in existing:
        _set_meta(connection, "schema_version", str(DATA_TABLE_SCHEMA_VERSION))
    if "scope" not in existing:
        _set_meta(connection, "scope", scope)
    if flow_id is not None and "flow_id" not in existing:
        _set_meta(connection, "flow_id", flow_id)
    if session_id is not None and "session_id" not in existing:
        _set_meta(connection, "session_id", session_id)
    if "created_at" not in existing:
        _set_meta(connection, "created_at", utcnow().replace(microsecond=0).isoformat())
    _import_foreign_tables(connection)


def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    _ = _execute(
        connection,
        _sql(
            f"INSERT INTO {PLATFORM_META_TABLE}(key, value) VALUES (?, ?) ",
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ),
        (key, value),
    )


def _meta_map(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        _row_str(row, "key"): _row_str(row, "value")
        for row in _fetchall(connection, f"SELECT key, value FROM {PLATFORM_META_TABLE}")
    }


def _import_foreign_tables(connection: sqlite3.Connection) -> None:
    master_rows = _fetchall(
        connection, "SELECT name FROM sqlite_master WHERE type = 'table'"
    )
    registered = {
        _row_str(row, "table_name")
        for row in _fetchall(
            connection, f"SELECT DISTINCT table_name FROM {PLATFORM_COLUMNS_TABLE}"
        )
    }
    for row in master_rows:
        table_name = _row_str(row, "name")
        if not is_user_table_name(table_name):
            continue
        if table_name in registered:
            continue
        info = _fetchall(connection, f"PRAGMA table_info({quote_sql_ident(table_name)})")
        position = 0
        for column in info:
            column_name = _row_str(column, "name")
            if column_name in SYSTEM_COLUMNS:
                continue
            declared = _row_str(column, "type").upper()
            column_type = _sqlite_decl_to_column_type(declared)
            _ = _execute(
                connection,
                _sql(
                    f"INSERT INTO {PLATFORM_COLUMNS_TABLE} ",
                    "(table_name, column_name, column_type, position, not_null) ",
                    "VALUES (?, ?, ?, ?, ?)",
                ),
                (
                    table_name,
                    column_name,
                    column_type,
                    position,
                    1 if _row_int(column, "notnull") != 0 else 0,
                ),
            )
            position += 1


def _sqlite_decl_to_column_type(declared: str) -> DataTableColumnType:
    if "INT" in declared:
        return "integer"
    if declared in {"REAL", "FLOAT", "DOUBLE", "NUMERIC"}:
        return "real"
    if declared in {"BOOLEAN", "BOOL"}:
        return "boolean"
    return "text"


def create_user_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    columns: list[DataTableColumnSpec],
) -> None:
    name = validate_ident(table_name, kind="table")
    existing = _fetchone(
        connection,
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    )
    if existing is not None:
        raise ValueError(f"table {name!r} already exists")
    if not columns:
        raise ValueError(f"table {name!r} requires at least one column")
    seen: set[str] = set()
    column_sql: list[str] = [
        "row_id INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at TEXT NOT NULL",
        "updated_at TEXT NOT NULL",
    ]
    for index, spec in enumerate(columns):
        column_name = validate_ident(spec.name, kind="column")
        if column_name in seen:
            raise ValueError(f"duplicate column {column_name!r}")
        seen.add(column_name)
        sql_type = _SQLITE_TYPE[spec.column_type]
        null_sql = " NOT NULL" if spec.not_null else ""
        column_sql.append(f"{quote_sql_ident(column_name)} {sql_type}{null_sql}")
        _ = _execute(
            connection,
            _sql(
                f"INSERT INTO {PLATFORM_COLUMNS_TABLE} ",
                "(table_name, column_name, column_type, position, not_null) ",
                "VALUES (?, ?, ?, ?, ?)",
            ),
            (name, column_name, spec.column_type, index, 1 if spec.not_null else 0),
        )
    _ = _execute(
        connection,
        f"CREATE TABLE {quote_sql_ident(name)} ({', '.join(column_sql)})",
    )


def add_user_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    spec: DataTableColumnSpec,
) -> None:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    column_name = validate_ident(spec.name, kind="column")
    existing = _fetchone(
        connection,
        f"SELECT 1 FROM {PLATFORM_COLUMNS_TABLE} WHERE table_name = ? AND column_name = ?",
        (name, column_name),
    )
    if existing is not None:
        raise ValueError(f"column {column_name!r} already exists on {name}")
    max_pos = _fetchone(
        connection,
        _sql(
            f"SELECT COALESCE(MAX(position), -1) AS position FROM {PLATFORM_COLUMNS_TABLE} ",
            "WHERE table_name = ?",
        ),
        (name,),
    )
    if max_pos is None:
        raise ValueError(f"cannot resolve column position for {name}")
    position = _row_int(max_pos, "position") + 1
    sql_type = _SQLITE_TYPE[spec.column_type]
    null_sql = " NOT NULL" if spec.not_null else ""
    _ = _execute(
        connection,
        _sql(
            f"ALTER TABLE {quote_sql_ident(name)} ADD COLUMN ",
            f"{quote_sql_ident(column_name)} {sql_type}{null_sql}",
        ),
    )
    _ = _execute(
        connection,
        _sql(
            f"INSERT INTO {PLATFORM_COLUMNS_TABLE} ",
            "(table_name, column_name, column_type, position, not_null) ",
            "VALUES (?, ?, ?, ?, ?)",
        ),
        (name, column_name, spec.column_type, position, 1 if spec.not_null else 0),
    )


def read_schema_snapshot(connection: sqlite3.Connection) -> DataTableSchemaSnapshot:
    meta = _meta_map(connection)
    scope_raw = meta.get("scope")
    if scope_raw == "flow_asset" or scope_raw == "flow_session" or scope_raw == "office_document":
        scope: DataTableScope = scope_raw
    else:
        raise ValueError("data table _platform_meta.scope is missing or invalid")
    schema_version_raw = meta.get("schema_version")
    if schema_version_raw is None:
        raise ValueError("data table _platform_meta.schema_version is missing")
    tables: list[DataTableTableSnapshot] = []
    table_rows = _fetchall(
        connection,
        f"SELECT DISTINCT table_name FROM {PLATFORM_COLUMNS_TABLE} ORDER BY table_name",
    )
    for table_row in table_rows:
        table_name = _row_str(table_row, "table_name")
        columns = _table_columns(connection, table_name)
        count_row = _fetchone(
            connection, f"SELECT COUNT(*) AS n FROM {quote_sql_ident(table_name)}"
        )
        if count_row is None:
            raise ValueError(f"cannot count rows in {table_name}")
        tables.append(
            DataTableTableSnapshot(
                name=table_name,
                row_count=_row_int(count_row, "n"),
                columns=columns,
            )
        )
    return DataTableSchemaSnapshot(
        schema_version=int(schema_version_raw),
        scope=scope,
        flow_id=meta.get("flow_id"),
        session_id=meta.get("session_id"),
        tables=tables,
    )


def _parse_column_type(raw: str, *, table_name: str, column_name: str) -> DataTableColumnType:
    if raw == "text":
        return "text"
    if raw == "integer":
        return "integer"
    if raw == "real":
        return "real"
    if raw == "boolean":
        return "boolean"
    if raw == "datetime":
        return "datetime"
    if raw == "json":
        return "json"
    if raw == "file_ref":
        return "file_ref"
    raise ValueError(f"unknown column_type {raw!r} on {table_name}.{column_name}")


def _table_columns(
    connection: sqlite3.Connection, table_name: str
) -> list[DataTableColumnSnapshot]:
    rows = _fetchall(
        connection,
        _sql(
            f"SELECT column_name, column_type, not_null FROM {PLATFORM_COLUMNS_TABLE} ",
            "WHERE table_name = ? ORDER BY position",
        ),
        (table_name,),
    )
    columns: list[DataTableColumnSnapshot] = []
    for row in rows:
        column_name = _row_str(row, "column_name")
        column_type = _parse_column_type(
            _row_str(row, "column_type"),
            table_name=table_name,
            column_name=column_name,
        )
        columns.append(
            DataTableColumnSnapshot(
                name=column_name,
                column_type=column_type,
                not_null=_row_int(row, "not_null") != 0,
            )
        )
    return columns


def _require_user_table(connection: sqlite3.Connection, table_name: str) -> None:
    row = _fetchone(
        connection,
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    if row is None:
        raise ValueError(f"table {table_name!r} does not exist")


def _column_type_map(
    connection: sqlite3.Connection, table_name: str
) -> dict[str, DataTableColumnSnapshot]:
    return {column.name: column for column in _table_columns(connection, table_name)}


_BOOLEAN_TRUE = frozenset({"true", "1", "yes"})
_BOOLEAN_FALSE = frozenset({"false", "0", "no"})


def coerce_cell(column: DataTableColumnSnapshot, value: JsonValue) -> object:
    """Typed cell write. Excel/UI may send strings; empty → NULL when nullable."""
    parsed: JsonValue = value
    if isinstance(value, str) and value.strip() == "":
        parsed = None
    if parsed is None:
        if column.not_null:
            raise ValueError(f"column {column.name!r} is not_null")
        return None
    column_type = column.column_type
    if column_type == "text":
        if not isinstance(parsed, str):
            raise ValueError(f"column {column.name!r} expects text")
        return parsed
    if column_type == "integer":
        return _coerce_integer(column.name, parsed)
    if column_type == "real":
        return _coerce_real(column.name, parsed)
    if column_type == "boolean":
        return _coerce_boolean(column.name, parsed)
    if column_type == "datetime":
        if not isinstance(parsed, str):
            raise ValueError(f"column {column.name!r} expects datetime ISO string")
        try:
            return _parse_datetime(parsed.strip()).isoformat()
        except ValueError as exc:
            raise ValueError(
                f"column {column.name!r} expects datetime ISO string"
            ) from exc
    if column_type == "json":
        payload: JsonValue
        if isinstance(parsed, str):
            payload = parse_json_value(parsed, column.name)
        else:
            payload = parsed
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if column_type == "file_ref":
        if not isinstance(parsed, str) or not parsed.strip():
            raise ValueError(f"column {column.name!r} expects file_id")
        return parsed.strip()
    raise ValueError(f"unsupported column_type {column_type}")


def _coerce_integer(column_name: str, value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"column {column_name!r} expects integer")
    if isinstance(value, int):
        return value
    stripped = value.strip()
    negative = stripped.startswith("-")
    digits = stripped[1:] if negative else stripped
    if digits.isdigit() and digits != "":
        return int(stripped)
    raise ValueError(f"column {column_name!r} expects integer")


def _coerce_real(column_name: str, value: JsonValue) -> float:
    if isinstance(value, bool):
        raise ValueError(f"column {column_name!r} expects real")
    if isinstance(value, (int, float)):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"column {column_name!r} expects real")
        return parsed
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"column {column_name!r} expects real") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"column {column_name!r} expects real")
        return parsed
    raise ValueError(f"column {column_name!r} expects real")


def _coerce_boolean(column_name: str, value: JsonValue) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _BOOLEAN_TRUE:
            return 1
        if token in _BOOLEAN_FALSE:
            return 0
    raise ValueError(f"column {column_name!r} expects boolean")


def decode_cell(column: DataTableColumnSnapshot, raw: object) -> JsonValue:
    if raw is None:
        return None
    column_type = column.column_type
    if column_type == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int):
            return raw != 0
        raise ValueError(f"column {column.name!r} boolean cell is invalid")
    if column_type == "json":
        if not isinstance(raw, str):
            raise ValueError(f"column {column.name!r} json cell must be text")
        return parse_json_value(raw, column.name)
    if column_type == "integer":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(f"column {column.name!r} integer cell is invalid")
        return raw
    if column_type == "real":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"column {column.name!r} real cell is invalid")
        return float(raw)
    if isinstance(raw, (str, int, float)):
        return raw
    raise ValueError(f"column {column.name!r} has unsupported stored value")


def insert_rows(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    rows: list[JsonObject],
) -> list[int]:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    columns = _column_type_map(connection, name)
    now = utcnow().replace(microsecond=0).isoformat()
    inserted: list[int] = []
    for row in rows:
        unknown = set(row) - set(columns)
        if unknown:
            raise ValueError(f"unknown columns for {name}: {sorted(unknown)}")
        names = list(columns)
        placeholders = ", ".join("?" for _ in names)
        quoted = ", ".join(quote_sql_ident(col) for col in names)
        values = [coerce_cell(columns[col], row.get(col)) for col in names]
        cursor = _execute(
            connection,
            _sql(
                f"INSERT INTO {quote_sql_ident(name)} (created_at, updated_at, {quoted}) ",
                f"VALUES (?, ?, {placeholders})",
            ),
            [now, now, *values],
        )
        row_id = cursor.lastrowid
        if row_id is None:
            raise ValueError(f"insert into {name} did not return row_id")
        inserted.append(int(row_id))
    return inserted


def update_row(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    row_id: int,
    values: JsonObject,
) -> None:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    if not values:
        raise ValueError("update values are required")
    columns = _column_type_map(connection, name)
    unknown = set(values) - set(columns)
    if unknown:
        raise ValueError(f"unknown columns for {name}: {sorted(unknown)}")
    assignments = ["updated_at = ?"]
    params: list[object] = [utcnow().replace(microsecond=0).isoformat()]
    for column_name, raw in values.items():
        assignments.append(f"{quote_sql_ident(column_name)} = ?")
        params.append(coerce_cell(columns[column_name], raw))
    params.append(row_id)
    cursor = _execute(
        connection,
        f"UPDATE {quote_sql_ident(name)} SET {', '.join(assignments)} WHERE row_id = ?",
        params,
    )
    if cursor.rowcount != 1:
        raise ValueError(f"row_id {row_id} not found in {name}")


def delete_rows(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    row_ids: list[int],
) -> int:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    if not row_ids:
        raise ValueError("row_ids are required")
    placeholders = ", ".join("?" for _ in row_ids)
    cursor = _execute(
        connection,
        f"DELETE FROM {quote_sql_ident(name)} WHERE row_id IN ({placeholders})",
        row_ids,
    )
    return int(cursor.rowcount)


def _like_contains_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _append_column_q_clauses(
    *,
    columns: dict[str, DataTableColumnSnapshot],
    column_q: list[str] | None,
    clauses: list[str],
    params: list[object],
) -> None:
    if column_q is None:
        return
    for raw in column_q:
        if ":" not in raw:
            raise ValueError("column_q must be column:query")
        column_name, query = raw.split(":", 1)
        ident = validate_ident(column_name, kind="column")
        if ident not in columns and ident not in SYSTEM_COLUMNS:
            raise ValueError(f"unknown column_q column {ident!r}")
        trimmed = query.strip()
        if trimmed == "":
            raise ValueError("column_q query must be non-empty")
        if len(trimmed) > MAX_SEARCH_Q_LENGTH:
            raise ValueError(
                f"column_q query must be at most {MAX_SEARCH_Q_LENGTH} characters"
            )
        clauses.append(
            f"CAST({quote_sql_ident(ident)} AS TEXT) LIKE ? ESCAPE '\\'"
        )
        params.append(_like_contains_pattern(trimmed))


def page_rows(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    limit: int,
    cursor: str | None = None,
    sort_column: str | None = None,
    sort_dir: Literal["asc", "desc"] = "asc",
    filter_column: str | None = None,
    filter_value: str | None = None,
    q: str | None = None,
    column_q: list[str] | None = None,
) -> CursorPage[DataTableRow]:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    if limit < 1 or limit > 200:
        raise ValueError("limit must be 1..200")
    columns = _column_type_map(connection, name)
    order_column = "row_id"
    if sort_column is not None:
        sort_name = validate_ident(sort_column, kind="column")
        if sort_name not in columns and sort_name not in SYSTEM_COLUMNS:
            raise ValueError(f"unknown sort column {sort_name!r}")
        order_column = sort_name
    direction = "ASC" if sort_dir == "asc" else "DESC"
    clauses: list[str] = []
    params: list[object] = []
    if filter_column is not None:
        filter_name = validate_ident(filter_column, kind="column")
        if filter_name not in columns and filter_name not in SYSTEM_COLUMNS:
            raise ValueError(f"unknown filter column {filter_name!r}")
        if filter_value is None:
            raise ValueError("filter_value is required when filter_column is set")
        clauses.append(f"{quote_sql_ident(filter_name)} = ?")
        params.append(filter_value)
    if q is not None:
        query = q.strip()
        if query == "":
            raise ValueError("q must be non-empty")
        if len(query) > MAX_SEARCH_Q_LENGTH:
            raise ValueError(f"q must be at most {MAX_SEARCH_Q_LENGTH} characters")
        text_names = [
            column_name
            for column_name, column in columns.items()
            if column.column_type == "text"
        ]
        if text_names:
            like = _like_contains_pattern(query)
            ors = " OR ".join(
                f"{quote_sql_ident(column_name)} LIKE ? ESCAPE '\\'"
                for column_name in text_names
            )
            clauses.append(f"({ors})")
            params.extend([like] * len(text_names))
        else:
            clauses.append("0 = 1")
    _append_column_q_clauses(
        columns=columns,
        column_q=column_q,
        clauses=clauses,
        params=params,
    )
    if cursor is not None:
        created_at, entity_id = decode_cursor(cursor)
        clauses.append(
            f"({quote_sql_ident('created_at')}, {quote_sql_ident('row_id')}) > (?, ?)"
        )
        params.append(created_at.isoformat())
        params.append(int(entity_id))
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    fetch_limit = limit + 1
    sql = _sql(
        f"SELECT * FROM {quote_sql_ident(name)}{where_sql} ",
        f"ORDER BY {quote_sql_ident(order_column)} {direction}, row_id ASC ",
        f"LIMIT {fetch_limit}",
    )
    fetched = _fetchall(connection, sql, params)
    has_more = len(fetched) > limit
    page = fetched[:limit]
    items = [_data_table_row_from_sqlite(sqlite_row, columns) for sqlite_row in page]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(_parse_datetime(last.created_at), str(last.row_id))
    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)


def _data_table_row_from_sqlite(
    sqlite_row: sqlite3.Row,
    columns: dict[str, DataTableColumnSnapshot],
) -> DataTableRow:
    values: JsonObject = {}
    for column_name, column in columns.items():
        values[column_name] = decode_cell(column, _row_get(sqlite_row, column_name))
    return DataTableRow(
        row_id=_row_int(sqlite_row, "row_id"),
        created_at=_row_str(sqlite_row, "created_at"),
        updated_at=_row_str(sqlite_row, "updated_at"),
        values=values,
    )


def list_table_rows(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    max_rows: int = MAX_EXPORT_ROWS,
) -> tuple[list[DataTableColumnSnapshot], list[DataTableRow]]:
    name = validate_ident(table_name, kind="table")
    _require_user_table(connection, name)
    if max_rows < 1:
        raise ValueError("max_rows must be >= 1")
    columns = _column_type_map(connection, name)
    ordered = list(columns.values())
    sql = _sql(
        f"SELECT * FROM {quote_sql_ident(name)} ",
        "ORDER BY row_id ASC ",
        f"LIMIT {max_rows + 1}",
    )
    fetched = _fetchall(connection, sql, [])
    if len(fetched) > max_rows:
        raise ValueError(f"export exceeds {max_rows} rows")
    items = [_data_table_row_from_sqlite(sqlite_row, columns) for sqlite_row in fetched]
    return ordered, items


def execute_user_sql(
    connection: sqlite3.Connection,
    sql: str,
) -> tuple[list[str], list[list[JsonValue]]]:
    cursor = _execute(connection, sql)
    description = cursor.description
    if description is None:
        return [], []
    columns: list[str] = []
    for item in description:
        name = item[0]
        if not isinstance(name, str) or name == "":
            raise ValueError("user SQL result column name is required")
        columns.append(name)
    rows: list[list[JsonValue]] = []
    for fetched in cast(Sequence[sqlite3.Row], cursor.fetchall()):
        cells: list[JsonValue] = []
        for column_name in columns:
            value = _row_get(fetched, column_name)
            if value is None or isinstance(value, (str, int, float, bool)):
                cells.append(value)
            else:
                cells.append(str(value))
        rows.append(cells)
    return columns, rows


def schema_summary_text(connection: sqlite3.Connection) -> str:
    snapshot = read_schema_snapshot(connection)
    lines = [
        f"DataTable schema_version={snapshot.schema_version} scope={snapshot.scope}",
    ]
    if snapshot.flow_id is not None:
        lines.append(f"flow_id={snapshot.flow_id}")
    if snapshot.session_id is not None:
        lines.append(f"session_id={snapshot.session_id}")
    if not snapshot.tables:
        lines.append("tables: none")
        return "\n".join(lines)
    for table in snapshot.tables:
        column_desc = ", ".join(
            f"{column.name}:{column.column_type}" for column in table.columns
        )
        lines.append(f"table {table.name} rows={table.row_count} columns=[{column_desc}]")
    return "\n".join(lines)


def summarize_sqlite_bytes(raw: bytes) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    path = Path(tmp.name)
    _ = tmp.write(raw)
    tmp.close()
    connection = open_sqlite(path)
    try:
        initialize_platform_schema(
            connection,
            scope="office_document",
            flow_id=None,
            session_id=None,
        )
        return schema_summary_text(connection)
    finally:
        connection.close()
        if path.exists():
            path.unlink()
