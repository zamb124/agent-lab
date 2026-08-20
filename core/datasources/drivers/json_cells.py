"""DB cell → JSON на границе драйвера datasource."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from core.types import JsonObject, JsonValue, require_json_object, require_json_value


def json_cell(value: object) -> JsonValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return require_json_value(value, "datasource.cell")


def json_row(record: Mapping[str, object], columns: list[str]) -> JsonObject:
    payload: dict[str, JsonValue] = {
        column: json_cell(record[column]) for column in columns
    }
    return require_json_object(payload, "datasource.row")
