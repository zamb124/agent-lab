"""Экспорт пользовательской таблицы в CSV/xlsx (обратная граница к import_tabular)."""

from __future__ import annotations

import csv
import io
import json
from typing import Literal

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from core.data_tables.models import DataTableRow
from core.documents.viewer.models import DataTableColumnSnapshot
from core.types import JsonValue

ExportFormat = Literal["csv", "xlsx"]
_EXCEL_SHEET_NAME_MAX = 31


def dump_tabular_bytes(
    columns: list[DataTableColumnSnapshot],
    rows: list[DataTableRow],
    *,
    table_name: str,
    source_format: ExportFormat,
) -> bytes:
    if source_format == "csv":
        return _dump_csv(columns, rows)
    return _dump_xlsx(columns, rows, table_name=table_name)


def _dump_csv(columns: list[DataTableColumnSnapshot], rows: list[DataTableRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([column.name for column in columns])
    for row in rows:
        writer.writerow([_csv_cell(row.values.get(column.name)) for column in columns])
    return buffer.getvalue().encode("utf-8-sig")


def _dump_xlsx(
    columns: list[DataTableColumnSnapshot],
    rows: list[DataTableRow],
    *,
    table_name: str,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    if not isinstance(sheet, Worksheet):
        raise TypeError("openpyxl active sheet must be a Worksheet")
    sheet.title = table_name[:_EXCEL_SHEET_NAME_MAX]
    _ = sheet.append([column.name for column in columns])
    for row in rows:
        _ = sheet.append([_excel_cell(row.values.get(column.name)) for column in columns])
    if sheet.max_row >= 1:
        sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _csv_cell(value: JsonValue | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _excel_cell(value: JsonValue | None) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
