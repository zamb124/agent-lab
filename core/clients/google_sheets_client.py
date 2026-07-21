"""
Async HTTP client for Google Sheets API v4 (+ Drive permissions for share).

Auth: Service Account JSON XOR OAuth access_token (same contract as GoogleDocsClient).
HTTP: get_httpx_client only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Final, Literal, Protocol, cast
from urllib.parse import quote

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import service_account as sa

from core.clients.google_sheets_models import (
    AddSheetResult,
    AppendRowsResult,
    BatchClearValuesResult,
    BatchUpdateValuesResult,
    BatchValueRangeResult,
    ClearValuesResult,
    DeleteSheetResult,
    DriveShareRole,
    InsertDataOption,
    RenameSheetResult,
    ShareResult,
    SheetListResult,
    SheetPropertiesBrief,
    SheetRowInput,
    SpreadsheetCreated,
    SpreadsheetMetadata,
    UpdateValuesResult,
    ValueInputOption,
    ValueRangeResult,
    ValueRangeWrite,
    ValueRenderOption,
    normalize_sheet_rows_for_write,
    parse_sheet_rows,
)
from core.clients.google_workspace_scopes import (
    GOOGLE_SCOPE_DRIVE_FILE,
    GOOGLE_SCOPE_SPREADSHEETS,
)
from core.config import get_settings
from core.config.models import GoogleWorkspaceApiBases
from core.http import get_httpx_client
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)

_DEFAULT_SHEETS_BASE: Final[str] = "https://sheets.googleapis.com/v4"
_DEFAULT_DRIVE_BASE: Final[str] = "https://www.googleapis.com/drive/v3"
_SA_SCOPES: Final[tuple[str, ...]] = (
    GOOGLE_SCOPE_SPREADSHEETS,
    GOOGLE_SCOPE_DRIVE_FILE,
)

_HttpMethod = Literal["GET", "POST", "PUT", "DELETE"]


class GoogleSheetsApiError(Exception):
    """HTTP error from Google Sheets / Drive API."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        google_error_status: str | None = None,
    ) -> None:
        self.status_code: int = status_code
        self.google_error_status: str | None = google_error_status
        super().__init__(f"Google Sheets API {status_code}: {message}")


class _GoogleCredentials(Protocol):
    valid: bool
    token: str | None

    def refresh(self, request: AuthRequest) -> None: ...

    def with_subject(self, subject: str) -> _GoogleCredentials: ...


class _FromServiceAccountInfo(Protocol):
    def __call__(
        self,
        info: JsonObject,
        *,
        scopes: list[str],
    ) -> _GoogleCredentials: ...


def spreadsheet_web_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def _resolve_api_base(
    explicit: str | None,
    from_settings: str | None,
    default: str,
) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.rstrip("/")
    if from_settings is not None and from_settings.strip() != "":
        return from_settings.rstrip("/")
    return default


class GoogleSheetsClient:
    """
    Typed Google Sheets API v4 client.

    Pass exactly one of credentials_json or access_token.
    subject — Workspace domain-wide delegation (SA only).
    """

    def __init__(
        self,
        *,
        credentials_json: str | None = None,
        access_token: str | None = None,
        subject: str | None = None,
        sheets_base: str | None = None,
        drive_base: str | None = None,
        api_bases: GoogleWorkspaceApiBases | None = None,
    ) -> None:
        if credentials_json and access_token:
            raise ValueError("Pass credentials_json or access_token, not both.")
        if not credentials_json and not access_token:
            raise ValueError(
                "Pass credentials_json (Service Account JSON) "
                + "or access_token (OAuth2 Bearer)."
            )
        if subject and not credentials_json:
            raise ValueError("subject (impersonation) requires credentials_json.")

        resolved_bases = api_bases
        if resolved_bases is None:
            resolved_bases = get_settings().google_workspace.api_bases
        self._sheets_base: str = _resolve_api_base(
            sheets_base,
            resolved_bases.sheets_base,
            _DEFAULT_SHEETS_BASE,
        )
        self._drive_base: str = _resolve_api_base(
            drive_base,
            resolved_bases.drive_base,
            _DEFAULT_DRIVE_BASE,
        )

        self._credentials: _GoogleCredentials | None = None
        self._static_token: str | None = None

        if credentials_json:
            info = parse_json_object(credentials_json, "google.service_account")
            if resolved_bases.token_uri is not None and resolved_bases.token_uri.strip() != "":
                info = {**info, "token_uri": resolved_bases.token_uri.strip()}
            from_service_account_info = cast(
                _FromServiceAccountInfo,
                sa.Credentials.from_service_account_info,
            )
            creds = from_service_account_info(info, scopes=list(_SA_SCOPES))
            if subject:
                creds = creds.with_subject(subject)
            self._credentials = creds
        else:
            self._static_token = access_token

    async def _auth_headers(self) -> dict[str, str]:
        if self._static_token:
            return {"Authorization": f"Bearer {self._static_token}"}
        credentials = self._credentials
        if credentials is None:
            raise RuntimeError("GoogleSheetsClient credentials are not configured")
        if not credentials.valid:
            # google-auth refresh is sync HTTP; to_thread avoids blocking the loop
            # (deadlock with local ASGI emulator serving /token).
            await asyncio.to_thread(credentials.refresh, AuthRequest())
        token = credentials.token
        if token is None or token == "":
            raise RuntimeError("GoogleSheetsClient did not produce access token")
        return {"Authorization": f"Bearer {token}"}

    async def _request(
        self,
        method: _HttpMethod,
        url: str,
        *,
        json_body: JsonObject | None = None,
        params: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> JsonObject:
        headers = await self._auth_headers()
        client = get_httpx_client(timeout=timeout)
        query = dict(params) if params is not None else None

        match method:
            case "GET":
                resp = await client.get(url, headers=headers, params=query)
            case "POST":
                resp = await client.post(
                    url, headers=headers, params=query, json=json_body
                )
            case "PUT":
                if json_body is None:
                    raise ValueError("GoogleSheetsClient PUT requires json_body")
                resp = await client.put(
                    url, headers=headers, params=query, json=json_body
                )
            case "DELETE":
                resp = await client.delete(url, headers=headers, params=query)

        if resp.status_code >= 400:
            google_status: str | None = None
            if resp.content:
                try:
                    err_payload = parse_json_object(
                        resp.content, "google.sheets.error"
                    )
                except (TypeError, ValueError):
                    err_payload = None
                if err_payload is not None:
                    error_obj = err_payload.get("error")
                    if isinstance(error_obj, Mapping):
                        status_val = error_obj.get("status")
                        if isinstance(status_val, str):
                            google_status = status_val
            raise GoogleSheetsApiError(
                resp.status_code,
                resp.text,
                google_error_status=google_status,
            )
        if resp.status_code == 204 or resp.content == b"":
            return {}
        return parse_json_object(resp.content, f"Google Sheets {method} {url}")

    @staticmethod
    def _require_id(spreadsheet_id: str) -> str:
        stripped = spreadsheet_id.strip()
        if stripped == "":
            raise ValueError("spreadsheet_id is required")
        return stripped

    @staticmethod
    def _require_range(range_a1: str) -> str:
        stripped = range_a1.strip()
        if stripped == "":
            raise ValueError("range must be non-empty A1 notation")
        return stripped

    @staticmethod
    def _encode_range(range_a1: str) -> str:
        return quote(range_a1, safe="!'")

    # ── spreadsheet create / metadata ─────────────────────────────

    async def create_spreadsheet(
        self,
        title: str,
        *,
        sheet_titles: Sequence[str] | None = None,
    ) -> SpreadsheetCreated:
        title_stripped = title.strip()
        if title_stripped == "":
            raise ValueError("title is required")
        body: JsonObject = {"properties": {"title": title_stripped}}
        if sheet_titles is not None:
            sheets_payload: list[JsonValue] = []
            for index, sheet_title in enumerate(sheet_titles):
                sheet_name = sheet_title.strip()
                if sheet_name == "":
                    raise ValueError("sheet_titles entries must be non-empty")
                sheets_payload.append(
                    {
                        "properties": {
                            "title": sheet_name,
                            "index": index,
                        }
                    }
                )
            body["sheets"] = sheets_payload
        raw = await self._request("POST", f"{self._sheets_base}/spreadsheets", json_body=body)
        spreadsheet_id = raw.get("spreadsheetId")
        if not isinstance(spreadsheet_id, str) or spreadsheet_id == "":
            raise GoogleSheetsApiError(500, "create response missing spreadsheetId")
        props = raw.get("properties")
        resolved_title = title_stripped
        if isinstance(props, Mapping):
            title_val = props.get("title")
            if isinstance(title_val, str) and title_val != "":
                resolved_title = title_val
        return SpreadsheetCreated(
            spreadsheet_id=spreadsheet_id,
            title=resolved_title,
            web_url=spreadsheet_web_url(spreadsheet_id),
        )

    async def get_metadata(self, spreadsheet_id: str) -> SpreadsheetMetadata:
        sid = self._require_id(spreadsheet_id)
        fields = "spreadsheetId,properties.title,sheets.properties(sheetId,title,index)"
        raw = await self._request(
            "GET",
            f"{self._sheets_base}/spreadsheets/{sid}",
            params={"fields": fields},
        )
        return self._parse_metadata(raw, fallback_id=sid)

    async def list_sheets(self, spreadsheet_id: str) -> SheetListResult:
        meta = await self.get_metadata(spreadsheet_id)
        return SheetListResult(
            spreadsheet_id=meta.spreadsheet_id,
            titles=[sheet.title for sheet in meta.sheets],
        )

    def _parse_metadata(
        self, raw: JsonObject, *, fallback_id: str
    ) -> SpreadsheetMetadata:
        spreadsheet_id = raw.get("spreadsheetId")
        if not isinstance(spreadsheet_id, str) or spreadsheet_id == "":
            spreadsheet_id = fallback_id
        title = ""
        props = raw.get("properties")
        if isinstance(props, Mapping):
            title_val = props.get("title")
            if isinstance(title_val, str):
                title = title_val
        if title == "":
            raise GoogleSheetsApiError(500, "metadata missing properties.title")
        sheets: list[SheetPropertiesBrief] = []
        sheets_raw = raw.get("sheets")
        if isinstance(sheets_raw, list):
            for sheet_entry in sheets_raw:
                if not isinstance(sheet_entry, Mapping):
                    continue
                sheet_props = sheet_entry.get("properties")
                if not isinstance(sheet_props, Mapping):
                    continue
                sheet_id = sheet_props.get("sheetId")
                sheet_title = sheet_props.get("title")
                sheet_index = sheet_props.get("index")
                if (
                    isinstance(sheet_id, int)
                    and not isinstance(sheet_id, bool)
                    and isinstance(sheet_title, str)
                    and sheet_title != ""
                    and isinstance(sheet_index, int)
                    and not isinstance(sheet_index, bool)
                ):
                    sheets.append(
                        SheetPropertiesBrief(
                            sheet_id=sheet_id,
                            title=sheet_title,
                            index=sheet_index,
                        )
                    )
        return SpreadsheetMetadata(
            spreadsheet_id=spreadsheet_id,
            title=title,
            sheets=sheets,
            web_url=spreadsheet_web_url(spreadsheet_id),
        )

    # ── values ────────────────────────────────────────────────────

    async def get_values(
        self,
        spreadsheet_id: str,
        range_a1: str,
        *,
        value_render_option: ValueRenderOption = ValueRenderOption.FORMATTED_VALUE,
    ) -> ValueRangeResult:
        sid = self._require_id(spreadsheet_id)
        range_clean = self._require_range(range_a1)
        raw = await self._request(
            "GET",
            f"{self._sheets_base}/spreadsheets/{sid}/values/{self._encode_range(range_clean)}",
            params={"valueRenderOption": value_render_option.value},
        )
        returned_range = raw.get("range")
        range_out = (
            returned_range
            if isinstance(returned_range, str) and returned_range != ""
            else range_clean
        )
        return ValueRangeResult(
            range_a1=range_out,
            values=parse_sheet_rows(raw.get("values")),
        )

    async def batch_get_values(
        self,
        spreadsheet_id: str,
        ranges: Sequence[str],
        *,
        value_render_option: ValueRenderOption = ValueRenderOption.FORMATTED_VALUE,
    ) -> BatchValueRangeResult:
        sid = self._require_id(spreadsheet_id)
        if len(ranges) == 0:
            raise ValueError("ranges must be non-empty")
        clean_ranges = [self._require_range(r) for r in ranges]
        query_parts = [
            f"valueRenderOption={quote(value_render_option.value, safe='')}"
        ]
        for range_item in clean_ranges:
            query_parts.append(
                f"ranges={quote(range_item, safe=chr(33) + chr(39))}"
            )
        url = (
            f"{self._sheets_base}/spreadsheets/{sid}/values:batchGet"
            f"?{'&'.join(query_parts)}"
        )
        raw = await self._request("GET", url)
        value_ranges: list[ValueRangeResult] = []
        ranges_raw = raw.get("valueRanges")
        if isinstance(ranges_raw, list):
            for entry in ranges_raw:
                if not isinstance(entry, Mapping):
                    continue
                entry_obj = require_json_object(entry, "sheets.batchGet.valueRange")
                range_val = entry_obj.get("range")
                if not isinstance(range_val, str) or range_val == "":
                    raise GoogleSheetsApiError(500, "batchGet entry missing range")
                value_ranges.append(
                    ValueRangeResult(
                        range_a1=range_val,
                        values=parse_sheet_rows(entry_obj.get("values")),
                    )
                )
        return BatchValueRangeResult(spreadsheet_id=sid, value_ranges=value_ranges)

    async def update_values(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[SheetRowInput],
        *,
        value_input_option: ValueInputOption = ValueInputOption.USER_ENTERED,
    ) -> UpdateValuesResult:
        sid = self._require_id(spreadsheet_id)
        range_clean = self._require_range(range_a1)
        wire_values = normalize_sheet_rows_for_write(values)
        raw = await self._request(
            "PUT",
            f"{self._sheets_base}/spreadsheets/{sid}/values/{self._encode_range(range_clean)}",
            params={"valueInputOption": value_input_option.value},
            json_body={
                "range": range_clean,
                "majorDimension": "ROWS",
                "values": wire_values,
            },
        )
        return self._parse_update_values(raw, fallback_id=sid)

    async def batch_update_values(
        self,
        spreadsheet_id: str,
        data: Sequence[ValueRangeWrite],
        *,
        value_input_option: ValueInputOption = ValueInputOption.USER_ENTERED,
    ) -> BatchUpdateValuesResult:
        sid = self._require_id(spreadsheet_id)
        if len(data) == 0:
            raise ValueError("data must be non-empty")
        data_payload: list[JsonValue] = []
        for item in data:
            data_payload.append(
                {
                    "range": item.range_a1,
                    "majorDimension": "ROWS",
                    "values": normalize_sheet_rows_for_write(item.values),
                }
            )
        raw = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}/values:batchUpdate",
            json_body={
                "valueInputOption": value_input_option.value,
                "data": data_payload,
            },
        )
        responses: list[UpdateValuesResult] = []
        responses_raw = raw.get("responses")
        if isinstance(responses_raw, list):
            for entry in responses_raw:
                if isinstance(entry, Mapping):
                    responses.append(
                        self._parse_update_values(
                            require_json_object(entry, "sheets.batchUpdate.response"),
                            fallback_id=sid,
                        )
                    )
        return BatchUpdateValuesResult(
            spreadsheet_id=sid,
            total_updated_rows=_optional_int(raw.get("totalUpdatedRows")),
            total_updated_columns=_optional_int(raw.get("totalUpdatedColumns")),
            total_updated_cells=_optional_int(raw.get("totalUpdatedCells")),
            total_updated_sheets=_optional_int(raw.get("totalUpdatedSheets")),
            responses=responses,
        )

    async def append_rows(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[SheetRowInput],
        *,
        value_input_option: ValueInputOption = ValueInputOption.USER_ENTERED,
        insert_data_option: InsertDataOption = InsertDataOption.INSERT_ROWS,
    ) -> AppendRowsResult:
        sid = self._require_id(spreadsheet_id)
        range_clean = self._require_range(range_a1)
        wire_values = normalize_sheet_rows_for_write(values)
        raw = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}/values/{self._encode_range(range_clean)}:append",
            params={
                "valueInputOption": value_input_option.value,
                "insertDataOption": insert_data_option.value,
            },
            json_body={
                "range": range_clean,
                "majorDimension": "ROWS",
                "values": wire_values,
            },
        )
        table_range = raw.get("tableRange")
        updates = raw.get("updates")
        update_result = UpdateValuesResult(spreadsheet_id=sid)
        if isinstance(updates, Mapping):
            update_result = self._parse_update_values(
                require_json_object(updates, "sheets.append.updates"),
                fallback_id=sid,
            )
        return AppendRowsResult(
            spreadsheet_id=sid,
            table_range=table_range if isinstance(table_range, str) else None,
            updated_range=update_result.updated_range,
            updated_rows=update_result.updated_rows,
            updated_columns=update_result.updated_columns,
            updated_cells=update_result.updated_cells,
        )

    async def clear_values(
        self, spreadsheet_id: str, range_a1: str
    ) -> ClearValuesResult:
        sid = self._require_id(spreadsheet_id)
        range_clean = self._require_range(range_a1)
        raw = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}/values/{self._encode_range(range_clean)}:clear",
            json_body={},
        )
        cleared = raw.get("clearedRange")
        if not isinstance(cleared, str) or cleared == "":
            cleared = range_clean
        return ClearValuesResult(spreadsheet_id=sid, cleared_range=cleared)

    async def batch_clear_values(
        self, spreadsheet_id: str, ranges: Sequence[str]
    ) -> BatchClearValuesResult:
        sid = self._require_id(spreadsheet_id)
        if len(ranges) == 0:
            raise ValueError("ranges must be non-empty")
        clean = [self._require_range(r) for r in ranges]
        raw = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}/values:batchClear",
            json_body={"ranges": clean},
        )
        cleared_raw = raw.get("clearedRanges")
        cleared: list[str] = []
        if isinstance(cleared_raw, list):
            for item in cleared_raw:
                if isinstance(item, str) and item != "":
                    cleared.append(item)
        return BatchClearValuesResult(spreadsheet_id=sid, cleared_ranges=cleared)

    def _parse_update_values(
        self, raw: JsonObject, *, fallback_id: str
    ) -> UpdateValuesResult:
        spreadsheet_id = raw.get("spreadsheetId")
        if not isinstance(spreadsheet_id, str) or spreadsheet_id == "":
            spreadsheet_id = fallback_id
        updated_range = raw.get("updatedRange")
        return UpdateValuesResult(
            spreadsheet_id=spreadsheet_id,
            updated_range=updated_range if isinstance(updated_range, str) else None,
            updated_rows=_optional_int(raw.get("updatedRows")),
            updated_columns=_optional_int(raw.get("updatedColumns")),
            updated_cells=_optional_int(raw.get("updatedCells")),
        )

    # ── structure (batchUpdate) ───────────────────────────────────

    async def add_sheet(
        self, spreadsheet_id: str, title: str
    ) -> AddSheetResult:
        sid = self._require_id(spreadsheet_id)
        title_clean = title.strip()
        if title_clean == "":
            raise ValueError("title is required")
        raw = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}:batchUpdate",
            json_body={
                "requests": [
                    {"addSheet": {"properties": {"title": title_clean}}}
                ]
            },
        )
        replies = raw.get("replies")
        if not isinstance(replies, list) or len(replies) == 0:
            raise GoogleSheetsApiError(500, "addSheet missing replies")
        first = replies[0]
        if not isinstance(first, Mapping):
            raise GoogleSheetsApiError(500, "addSheet reply invalid")
        add_sheet = first.get("addSheet")
        if not isinstance(add_sheet, Mapping):
            raise GoogleSheetsApiError(500, "addSheet reply missing addSheet")
        props = add_sheet.get("properties")
        if not isinstance(props, Mapping):
            raise GoogleSheetsApiError(500, "addSheet missing properties")
        sheet_id = props.get("sheetId")
        sheet_title = props.get("title")
        sheet_index = props.get("index")
        if (
            not isinstance(sheet_id, int)
            or isinstance(sheet_id, bool)
            or not isinstance(sheet_title, str)
            or sheet_title == ""
            or not isinstance(sheet_index, int)
            or isinstance(sheet_index, bool)
        ):
            raise GoogleSheetsApiError(500, "addSheet properties incomplete")
        return AddSheetResult(
            spreadsheet_id=sid,
            sheet_id=sheet_id,
            title=sheet_title,
            index=sheet_index,
        )

    async def rename_sheet(
        self, spreadsheet_id: str, sheet_id: int, title: str
    ) -> RenameSheetResult:
        sid = self._require_id(spreadsheet_id)
        title_clean = title.strip()
        if title_clean == "":
            raise ValueError("title is required")
        if sheet_id < 0:
            raise ValueError("sheet_id must be >= 0")
        _ = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}:batchUpdate",
            json_body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "title": title_clean,
                            },
                            "fields": "title",
                        }
                    }
                ]
            },
        )
        return RenameSheetResult(
            spreadsheet_id=sid, sheet_id=sheet_id, title=title_clean
        )

    async def delete_sheet(
        self, spreadsheet_id: str, sheet_id: int
    ) -> DeleteSheetResult:
        sid = self._require_id(spreadsheet_id)
        if sheet_id < 0:
            raise ValueError("sheet_id must be >= 0")
        _ = await self._request(
            "POST",
            f"{self._sheets_base}/spreadsheets/{sid}:batchUpdate",
            json_body={
                "requests": [{"deleteSheet": {"sheetId": sheet_id}}]
            },
        )
        return DeleteSheetResult(spreadsheet_id=sid, sheet_id=sheet_id)

    # ── Drive share ───────────────────────────────────────────────

    async def share(
        self,
        spreadsheet_id: str,
        *,
        role: DriveShareRole = DriveShareRole.READER,
        email: str | None = None,
        anyone: bool = False,
    ) -> ShareResult:
        sid = self._require_id(spreadsheet_id)
        if anyone and email is not None and email.strip() != "":
            raise ValueError("Pass either anyone=True or email, not both")
        if not anyone and (email is None or email.strip() == ""):
            raise ValueError("email is required when anyone=False")
        url = f"{self._drive_base}/files/{sid}/permissions"
        if anyone:
            _ = await self._request(
                "POST",
                url,
                json_body={"type": "anyone", "role": role.value},
            )
            return ShareResult(file_id=sid, role=role, anyone=True, email=None)
        email_clean = email.strip() if email is not None else ""
        _ = await self._request(
            "POST",
            url,
            json_body={
                "type": "user",
                "role": role.value,
                "emailAddress": email_clean,
            },
        )
        return ShareResult(
            file_id=sid, role=role, anyone=False, email=email_clean
        )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
