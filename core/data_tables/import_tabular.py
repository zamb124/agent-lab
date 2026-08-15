"""Импорт CSV/xlsx в пользовательскую таблицу SQLite (не в user sandbox)."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime
from typing import Literal

from openpyxl import load_workbook

from core.data_tables.identifiers import validate_ident
from core.data_tables.models import DataTableColumnSpec
from core.data_tables.sqlite_format import create_user_table, insert_rows
from core.types import JsonObject, JsonValue

_HEADER_RE_FALLBACK = "col"


def _header_to_ident(header: str, index: int) -> str:
    raw = header.strip().lower().replace(" ", "_").replace("-", "_")
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch == "_")
    if cleaned and cleaned[0].isalpha():
        try:
            return validate_ident(cleaned[:63], kind="column")
        except ValueError:
            pass
    return validate_ident(f"{_HEADER_RE_FALLBACK}_{index + 1}", kind="column")


def _cell_to_json(value: object) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def parse_tabular_bytes(
    raw: bytes,
    *,
    source_format: Literal["csv", "xlsx"],
) -> tuple[list[DataTableColumnSpec], list[JsonObject]]:
    if source_format == "csv":
        return _parse_csv(raw)
    return _parse_xlsx(raw)


def _parse_csv(raw: bytes) -> tuple[list[DataTableColumnSpec], list[JsonObject]]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")
    columns, name_by_header = _columns_from_headers(list(reader.fieldnames))
    rows: list[JsonObject] = []
    for record in reader:
        item: JsonObject = {}
        for header, column_name in name_by_header.items():
            item[column_name] = _cell_to_json(record.get(header))
        rows.append(item)
    return columns, rows


def _parse_xlsx(raw: bytes) -> tuple[list[DataTableColumnSpec], list[JsonObject]]:
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    iterator = sheet.iter_rows(values_only=True)
    header_row = next(iterator, None)
    if header_row is None:
        raise ValueError("xlsx sheet is empty")
    headers = ["" if cell is None else str(cell) for cell in header_row]
    columns, name_by_header = _columns_from_headers(headers)
    rows: list[JsonObject] = []
    for record in iterator:
        item: JsonObject = {}
        for index, header in enumerate(headers):
            column_name = name_by_header[header] if header in name_by_header else None
            if column_name is None:
                continue
            cell = record[index] if index < len(record) else None
            item[column_name] = _cell_to_json(cell)
        rows.append(item)
    return columns, rows


def _columns_from_headers(
    headers: list[str],
) -> tuple[list[DataTableColumnSpec], dict[str, str]]:
    if not headers:
        raise ValueError("tabular source has no columns")
    name_by_header: dict[str, str] = {}
    used: set[str] = set()
    columns: list[DataTableColumnSpec] = []
    for index, header in enumerate(headers):
        ident = _header_to_ident(header, index)
        unique = ident
        suffix = 2
        while unique in used:
            unique = validate_ident(f"{ident}_{suffix}"[:63], kind="column")
            suffix += 1
        used.add(unique)
        name_by_header[header] = unique
        columns.append(DataTableColumnSpec(name=unique, column_type="text"))
    return columns, name_by_header


def import_rows_into_new_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    columns: list[DataTableColumnSpec],
    rows: list[JsonObject],
) -> int:
    create_user_table(connection, table_name=table_name, columns=columns)
    inserted = insert_rows(connection, table_name=table_name, rows=rows)
    return len(inserted)
