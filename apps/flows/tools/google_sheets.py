"""
Platform tools for Google Sheets API v4.

Auth: resolve_google_workspace_auth (variables → user workspace OAuth →
prior docs/sheets credentials → company SA → OAuthInterrupt Connect Google).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.flows.src.services.platform_facades import resolve_google_workspace_auth
from apps.flows.src.tools.decorator import tool
from core.clients.google_sheets_client import GoogleSheetsClient
from core.clients.google_sheets_models import (
    DriveShareRole,
    InsertDataOption,
    SheetRowInput,
    ValueInputOption,
    ValueRangeWrite,
    ValueRenderOption,
)
from core.logging import get_logger
from core.types import JsonObject, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)

_TAGS = ["google_sheets"]


def _require_state(state: ExecutionState | None) -> ExecutionState:
    if state is None:
        raise ValueError("Google Sheets tools require ExecutionState")
    return state


async def _get_sheets_client(state: ExecutionState | None) -> GoogleSheetsClient:
    execution_state = _require_state(state)
    material = await resolve_google_workspace_auth(execution_state)
    return GoogleSheetsClient(
        credentials_json=material.credentials_json,
        access_token=material.access_token,
        subject=material.subject,
    )


def _tool_success(payload: BaseModel) -> JsonObject:
    dumped = require_json_object(
        payload.model_dump(mode="json"),
        "google_sheets.tool_payload",
    )
    return {"success": True, **dumped}


def _parse_value_input_option(raw: str) -> ValueInputOption:
    if raw == ValueInputOption.RAW.value:
        return ValueInputOption.RAW
    if raw == ValueInputOption.USER_ENTERED.value:
        return ValueInputOption.USER_ENTERED
    raise ValueError("value_input_option must be RAW or USER_ENTERED")


def _parse_insert_data_option(raw: str) -> InsertDataOption:
    if raw == InsertDataOption.OVERWRITE.value:
        return InsertDataOption.OVERWRITE
    if raw == InsertDataOption.INSERT_ROWS.value:
        return InsertDataOption.INSERT_ROWS
    raise ValueError("insert_data_option must be OVERWRITE or INSERT_ROWS")


def _parse_value_render_option(raw: str) -> ValueRenderOption:
    if raw == ValueRenderOption.FORMATTED_VALUE.value:
        return ValueRenderOption.FORMATTED_VALUE
    if raw == ValueRenderOption.UNFORMATTED_VALUE.value:
        return ValueRenderOption.UNFORMATTED_VALUE
    if raw == ValueRenderOption.FORMULA.value:
        return ValueRenderOption.FORMULA
    raise ValueError(
        "value_render_option must be FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA"
    )


def _parse_share_role(raw: str) -> DriveShareRole:
    if raw == DriveShareRole.READER.value:
        return DriveShareRole.READER
    if raw == DriveShareRole.COMMENTER.value:
        return DriveShareRole.COMMENTER
    if raw == DriveShareRole.WRITER.value:
        return DriveShareRole.WRITER
    raise ValueError("role must be reader, commenter, or writer")


# ── args ─────────────────────────────────────────────────────────


class SheetsCreateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, description="Spreadsheet title.")
    sheet_titles: list[str] | None = Field(
        None,
        description="Optional tab titles created with the spreadsheet.",
    )


class SheetsSpreadsheetIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(
        ...,
        min_length=1,
        description="Spreadsheet ID from the Google Sheets URL.",
    )


class SheetsGetValuesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    range: str = Field(
        ...,
        min_length=1,
        description="A1 range, e.g. Sheet1!A1:C10 or 'My Sheet'!A:A.",
    )
    value_render_option: str = Field(
        ValueRenderOption.FORMATTED_VALUE.value,
        description="FORMATTED_VALUE | UNFORMATTED_VALUE | FORMULA",
    )


class SheetsUpdateValuesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    range: str = Field(..., min_length=1)
    values: list[SheetRowInput] = Field(
        ...,
        description="Rows of cells (bool/string/number). Overwrites the range.",
    )
    value_input_option: str = Field(
        ValueInputOption.USER_ENTERED.value,
        description="RAW | USER_ENTERED (default USER_ENTERED).",
    )


class SheetsAppendRowsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    range: str = Field(
        ...,
        min_length=1,
        description=(
            "A1 range used to find the logical table; rows append after it "
            "(not the same as Sheets Tables API)."
        ),
    )
    values: list[SheetRowInput] = Field(..., min_length=1)
    value_input_option: str = Field(ValueInputOption.USER_ENTERED.value)
    insert_data_option: str = Field(
        InsertDataOption.INSERT_ROWS.value,
        description="OVERWRITE | INSERT_ROWS",
    )


class SheetsClearValuesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    range: str = Field(..., min_length=1)


class SheetsBatchGetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    ranges: list[str] = Field(..., min_length=1)
    value_render_option: str = Field(ValueRenderOption.FORMATTED_VALUE.value)


class SheetsBatchUpdateItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    range: str = Field(..., min_length=1)
    values: list[SheetRowInput] = Field(default_factory=list)

    @field_validator("range")
    @classmethod
    def _range_ok(cls, value: str) -> str:
        stripped = value.strip()
        if stripped == "":
            raise ValueError("range must be non-empty")
        return stripped


class SheetsBatchUpdateArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    data: list[SheetsBatchUpdateItem] = Field(..., min_length=1)
    value_input_option: str = Field(ValueInputOption.USER_ENTERED.value)


class SheetsBatchClearArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    ranges: list[str] = Field(..., min_length=1)


class SheetsShareArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    email: str | None = Field(None, description="Recipient email when anyone=false.")
    role: str = Field("reader", description="reader | commenter | writer")
    anyone: bool = Field(False, description="If true — anyone with the link.")


class SheetsAddSheetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)


class SheetsRenameSheetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    sheet_id: int = Field(..., ge=0)
    title: str = Field(..., min_length=1)


class SheetsDeleteSheetArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    spreadsheet_id: str = Field(..., min_length=1)
    sheet_id: int = Field(..., ge=0)


# ── tools ────────────────────────────────────────────────────────


@tool(
    name="sheets_create_spreadsheet",
    description=(
        "Creates a Google Spreadsheet. Optional sheet_titles creates tabs. "
        "Returns spreadsheet_id, title, web_url."
    ),
    tags=_TAGS,
    parameters_model=SheetsCreateArgs,
)
async def sheets_create_spreadsheet(
    title: str,
    sheet_titles: list[str] | None = None,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.create_spreadsheet(title, sheet_titles=sheet_titles)
    return _tool_success(result)


@tool(
    name="sheets_get_metadata",
    description=(
        "Returns spreadsheet title, web_url, and sheets "
        "[{sheet_id, title, index}]."
    ),
    tags=_TAGS,
    parameters_model=SheetsSpreadsheetIdArgs,
)
async def sheets_get_metadata(
    spreadsheet_id: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.get_metadata(spreadsheet_id)
    return _tool_success(result)


@tool(
    name="sheets_list_sheets",
    description="Lists tab titles in a spreadsheet.",
    tags=_TAGS,
    parameters_model=SheetsSpreadsheetIdArgs,
)
async def sheets_list_sheets(
    spreadsheet_id: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.list_sheets(spreadsheet_id)
    return _tool_success(result)


@tool(
    name="sheets_get_values",
    description=(
        "Reads a range (A1 notation). Empty trailing rows/columns are omitted "
        "by Google; missing values become []."
    ),
    tags=_TAGS,
    parameters_model=SheetsGetValuesArgs,
)
async def sheets_get_values(
    spreadsheet_id: str,
    range: str,
    value_render_option: str = ValueRenderOption.FORMATTED_VALUE.value,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.get_values(
        spreadsheet_id,
        range,
        value_render_option=_parse_value_render_option(value_render_option),
    )
    return _tool_success(result)


@tool(
    name="sheets_batch_get_values",
    description="Reads multiple A1 ranges in one call.",
    tags=_TAGS,
    parameters_model=SheetsBatchGetArgs,
)
async def sheets_batch_get_values(
    spreadsheet_id: str,
    ranges: list[str],
    value_render_option: str = ValueRenderOption.FORMATTED_VALUE.value,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.batch_get_values(
        spreadsheet_id,
        ranges,
        value_render_option=_parse_value_render_option(value_render_option),
    )
    return _tool_success(result)


@tool(
    name="sheets_update_values",
    description=(
        "Overwrites an A1 range with values (rows). "
        "Use USER_ENTERED so numbers/dates/formulas parse like the Sheets UI."
    ),
    tags=_TAGS,
    parameters_model=SheetsUpdateValuesArgs,
)
async def sheets_update_values(
    spreadsheet_id: str,
    range: str,
    values: list[SheetRowInput],
    value_input_option: str = ValueInputOption.USER_ENTERED.value,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.update_values(
        spreadsheet_id,
        range,
        values,
        value_input_option=_parse_value_input_option(value_input_option),
    )
    return _tool_success(result)


@tool(
    name="sheets_batch_update_values",
    description="Writes multiple ranges in one values.batchUpdate call.",
    tags=_TAGS,
    parameters_model=SheetsBatchUpdateArgs,
)
async def sheets_batch_update_values(
    spreadsheet_id: str,
    data: list[SheetsBatchUpdateItem],
    value_input_option: str = ValueInputOption.USER_ENTERED.value,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    writes: list[ValueRangeWrite] = []
    for item in data:
        # FunctionTool после model_dump отдаёт nested items как dict —
        # model_validate принимает и dict, и уже собранный SheetsBatchUpdateItem.
        parsed = SheetsBatchUpdateItem.model_validate(item)
        writes.append(ValueRangeWrite(range_a1=parsed.range, values=parsed.values))
    result = await client.batch_update_values(
        spreadsheet_id,
        writes,
        value_input_option=_parse_value_input_option(value_input_option),
    )
    return _tool_success(result)


@tool(
    name="sheets_append_rows",
    description=(
        "Appends rows after the logical table found in range (values.append). "
        "Not Google Sheets Tables API (addTable/tableId) — use this for normal "
        "ranges. Prefer INSERT_ROWS."
    ),
    tags=_TAGS,
    parameters_model=SheetsAppendRowsArgs,
)
async def sheets_append_rows(
    spreadsheet_id: str,
    range: str,
    values: list[SheetRowInput],
    value_input_option: str = ValueInputOption.USER_ENTERED.value,
    insert_data_option: str = InsertDataOption.INSERT_ROWS.value,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.append_rows(
        spreadsheet_id,
        range,
        values,
        value_input_option=_parse_value_input_option(value_input_option),
        insert_data_option=_parse_insert_data_option(insert_data_option),
    )
    return _tool_success(result)


@tool(
    name="sheets_clear_values",
    description="Clears cell values in an A1 range (keeps formatting).",
    tags=_TAGS,
    parameters_model=SheetsClearValuesArgs,
)
async def sheets_clear_values(
    spreadsheet_id: str,
    range: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.clear_values(spreadsheet_id, range)
    return _tool_success(result)


@tool(
    name="sheets_batch_clear_values",
    description="Clears multiple A1 ranges in one call.",
    tags=_TAGS,
    parameters_model=SheetsBatchClearArgs,
)
async def sheets_batch_clear_values(
    spreadsheet_id: str,
    ranges: list[str],
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.batch_clear_values(spreadsheet_id, ranges)
    return _tool_success(result)


@tool(
    name="sheets_share",
    description=(
        "Shares the spreadsheet via Drive permissions. "
        "Pass email or anyone=true."
    ),
    tags=_TAGS,
    parameters_model=SheetsShareArgs,
)
async def sheets_share(
    spreadsheet_id: str,
    email: str | None = None,
    role: str = "reader",
    anyone: bool = False,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.share(
        spreadsheet_id,
        role=_parse_share_role(role),
        email=email,
        anyone=anyone,
    )
    return _tool_success(result)


@tool(
    name="sheets_add_sheet",
    description="Adds a tab (AddSheet via spreadsheets.batchUpdate).",
    tags=_TAGS,
    parameters_model=SheetsAddSheetArgs,
)
async def sheets_add_sheet(
    spreadsheet_id: str,
    title: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.add_sheet(spreadsheet_id, title)
    return _tool_success(result)


@tool(
    name="sheets_rename_sheet",
    description="Renames a tab by sheet_id (from sheets_get_metadata).",
    tags=_TAGS,
    parameters_model=SheetsRenameSheetArgs,
)
async def sheets_rename_sheet(
    spreadsheet_id: str,
    sheet_id: int,
    title: str,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.rename_sheet(spreadsheet_id, sheet_id, title)
    return _tool_success(result)


@tool(
    name="sheets_delete_sheet",
    description="Deletes a tab by sheet_id.",
    tags=_TAGS,
    parameters_model=SheetsDeleteSheetArgs,
)
async def sheets_delete_sheet(
    spreadsheet_id: str,
    sheet_id: int,
    state: ExecutionState | None = None,
) -> JsonObject:
    client = await _get_sheets_client(state)
    result = await client.delete_sheet(spreadsheet_id, sheet_id)
    return _tool_success(result)


__all__ = [
    "sheets_create_spreadsheet",
    "sheets_get_metadata",
    "sheets_list_sheets",
    "sheets_get_values",
    "sheets_batch_get_values",
    "sheets_update_values",
    "sheets_batch_update_values",
    "sheets_append_rows",
    "sheets_clear_values",
    "sheets_batch_clear_values",
    "sheets_share",
    "sheets_add_sheet",
    "sheets_rename_sheet",
    "sheets_delete_sheet",
]
