"""Typed contracts for Google Sheets API v4 (values + spreadsheet structure)."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from core.models.base import StrictBaseModel
from core.types import JsonValue

SheetCell = str | float | bool
SheetCellInput = str | float | bool | int | None
SheetRow = list[SheetCell]
SheetRowInput = list[SheetCellInput]


class ValueInputOption(StrEnum):
    """https://developers.google.com/workspace/sheets/api/reference/rest/v4/ValueInputOption"""

    RAW = "RAW"
    USER_ENTERED = "USER_ENTERED"


class ValueRenderOption(StrEnum):
    """https://developers.google.com/workspace/sheets/api/reference/rest/v4/ValueRenderOption"""

    FORMATTED_VALUE = "FORMATTED_VALUE"
    UNFORMATTED_VALUE = "UNFORMATTED_VALUE"
    FORMULA = "FORMULA"


class InsertDataOption(StrEnum):
    """https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append#InsertDataOption"""

    OVERWRITE = "OVERWRITE"
    INSERT_ROWS = "INSERT_ROWS"


class DriveShareRole(StrEnum):
    READER = "reader"
    COMMENTER = "commenter"
    WRITER = "writer"


def normalize_sheet_cell(value: SheetCellInput) -> SheetCell | None:
    """
    Normalize a cell for Google Sheets wire format.

    Google accepts bool, string, double; null skips the cell on write.
    int is normalized to float.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    return value


def normalize_sheet_rows_for_write(
    rows: list[SheetRowInput],
) -> list[list[SheetCell | None]]:
    """Preserve column positions; None stays None (JSON null = skip cell)."""
    result: list[list[SheetCell | None]] = []
    for row in rows:
        out_row: list[SheetCell | None] = []
        for cell in row:
            out_row.append(normalize_sheet_cell(cell))
        result.append(out_row)
    return result


def parse_sheet_cell(value: JsonValue) -> SheetCell:
    """Parse a cell from Google values.get response."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    raise TypeError(f"Unexpected Sheet cell from Google API: {type(value).__name__}")


def parse_sheet_rows(raw_values: JsonValue) -> list[SheetRow]:
    if raw_values is None:
        return []
    if not isinstance(raw_values, list):
        raise TypeError("values must be a list of rows")
    rows: list[SheetRow] = []
    for row_raw in raw_values:
        if not isinstance(row_raw, list):
            raise TypeError("each values row must be a list")
        rows.append([parse_sheet_cell(cell) for cell in row_raw])
    return rows


class SheetPropertiesBrief(StrictBaseModel):
    sheet_id: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    index: int = Field(..., ge=0)


class SpreadsheetCreated(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    web_url: str = Field(..., min_length=1)


class SpreadsheetMetadata(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    sheets: list[SheetPropertiesBrief] = Field(default_factory=list)
    web_url: str = Field(..., min_length=1)


class ValueRangeResult(StrictBaseModel):
    range_a1: str = Field(..., min_length=1)
    values: list[SheetRow] = Field(default_factory=list)


class BatchValueRangeResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    value_ranges: list[ValueRangeResult] = Field(default_factory=list)


class UpdateValuesResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    updated_range: str | None = None
    updated_rows: int | None = None
    updated_columns: int | None = None
    updated_cells: int | None = None


class AppendRowsResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    table_range: str | None = None
    updated_range: str | None = None
    updated_rows: int | None = None
    updated_columns: int | None = None
    updated_cells: int | None = None


class ClearValuesResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    cleared_range: str = Field(..., min_length=1)


class BatchClearValuesResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    cleared_ranges: list[str] = Field(default_factory=list)


class BatchUpdateValuesResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    total_updated_rows: int | None = None
    total_updated_columns: int | None = None
    total_updated_cells: int | None = None
    total_updated_sheets: int | None = None
    responses: list[UpdateValuesResult] = Field(default_factory=list)


class SheetListResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    titles: list[str] = Field(default_factory=list)


class ShareResult(StrictBaseModel):
    file_id: str = Field(..., min_length=1)
    role: DriveShareRole
    anyone: bool = False
    email: str | None = None


class AddSheetResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    sheet_id: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)
    index: int = Field(..., ge=0)


class RenameSheetResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    sheet_id: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)


class DeleteSheetResult(StrictBaseModel):
    spreadsheet_id: str = Field(..., min_length=1)
    sheet_id: int = Field(..., ge=0)


class ValueRangeWrite(StrictBaseModel):
    """One range payload for values.batchUpdate."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    range_a1: str = Field(..., min_length=1)
    values: list[SheetRowInput] = Field(default_factory=list)

    @field_validator("range_a1")
    @classmethod
    def _range_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("range_a1 must be non-empty A1 notation")
        return stripped
