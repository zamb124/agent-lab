"""FastAPI app implementing Google REST surfaces used by platform clients."""

from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import unquote

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

from core.types import JsonObject, JsonValue, require_json_object
from tests.fixtures.google_api_emulator.store import (
    DocumentRecord,
    EmulatorStore,
    SheetTab,
    document_to_json,
    google_error,
    spreadsheet_to_json,
)


def create_google_api_emulator_app(store: EmulatorStore) -> FastAPI:
    app = FastAPI(title="platform-google-api-emulator")
    app.state.store = store

    def _auth(authorization: str | None) -> JSONResponse | None:
        if not store.is_authorized(authorization):
            return JSONResponse(
                status_code=401,
                content=google_error(
                    401,
                    "UNAUTHENTICATED",
                    "Request is missing required authentication credential.",
                ),
            )
        return None

    @app.post("/token")
    async def oauth_token(request: Request) -> JSONResponse:
        _ = await request.body()
        token = "sa-company"
        store.allow_token(token)
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

    @app.post("/v4/spreadsheets")
    async def create_spreadsheet(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        body = require_json_object(await request.json(), "emulator.create_spreadsheet")
        props = body.get("properties")
        title = "Untitled"
        if isinstance(props, dict):
            raw_title = props.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                title = raw_title.strip()
        sheet_titles: list[str] | None = None
        sheets_raw = body.get("sheets")
        if isinstance(sheets_raw, list) and sheets_raw:
            sheet_titles = []
            for item in sheets_raw:
                if not isinstance(item, dict):
                    continue
                sheet_props = item.get("properties")
                if isinstance(sheet_props, dict):
                    sheet_title = sheet_props.get("title")
                    if isinstance(sheet_title, str) and sheet_title.strip():
                        sheet_titles.append(sheet_title.strip())
        record = store.create_spreadsheet(title, sheet_titles)
        return JSONResponse(spreadsheet_to_json(record))

    @app.get("/v4/spreadsheets/{spreadsheet_id}")
    async def get_spreadsheet(
        spreadsheet_id: str,
        authorization: Annotated[str | None, Header()] = None,
        fields: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        _ = fields
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        return JSONResponse(spreadsheet_to_json(record))

    @app.get("/v4/spreadsheets/{spreadsheet_id}/values:batchGet")
    async def batch_get_values(
        spreadsheet_id: str,
        authorization: Annotated[str | None, Header()] = None,
        ranges: Annotated[list[str] | None, Query()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        value_ranges: list[JsonObject] = []
        for range_a1 in ranges or []:
            values = _read_range(record.sheets, range_a1)
            value_ranges.append(
                {"range": range_a1, "majorDimension": "ROWS", "values": values}
            )
        return JSONResponse(
            {"spreadsheetId": spreadsheet_id, "valueRanges": value_ranges}
        )

    @app.post("/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate")
    async def batch_update_values(
        spreadsheet_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        body = require_json_object(await request.json(), "emulator.batch_update_values")
        data = body.get("data")
        replies: list[JsonObject] = []
        total_cells = 0
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                range_a1 = item.get("range")
                values = item.get("values")
                if not isinstance(range_a1, str) or not isinstance(values, list):
                    continue
                updated = _write_range(record.sheets, range_a1, values)
                total_cells += updated["cells"]
                replies.append(
                    {
                        "spreadsheetId": spreadsheet_id,
                        "updatedRange": range_a1,
                        "updatedRows": updated["rows"],
                        "updatedColumns": updated["cols"],
                        "updatedCells": updated["cells"],
                    }
                )
        return JSONResponse(
            {
                "spreadsheetId": spreadsheet_id,
                "totalUpdatedCells": total_cells,
                "responses": replies,
            }
        )

    @app.post("/v4/spreadsheets/{spreadsheet_id}/values:batchClear")
    async def batch_clear_values(
        spreadsheet_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        body = require_json_object(await request.json(), "emulator.batch_clear")
        ranges = body.get("ranges")
        cleared: list[str] = []
        if isinstance(ranges, list):
            for range_a1 in ranges:
                if isinstance(range_a1, str):
                    _clear_range(record.sheets, range_a1)
                    cleared.append(range_a1)
        return JSONResponse(
            {"spreadsheetId": spreadsheet_id, "clearedRanges": cleared}
        )

    @app.api_route(
        "/v4/spreadsheets/{spreadsheet_id}/values/{range_path:path}",
        methods=["GET", "PUT", "POST"],
    )
    async def values_path(
        spreadsheet_id: str,
        range_path: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        valueInputOption: Annotated[str | None, Query()] = None,
        insertDataOption: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        _ = valueInputOption
        _ = insertDataOption
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        decoded = unquote(range_path)
        if decoded.endswith(":append") and request.method == "POST":
            range_a1 = decoded[: -len(":append")]
            body = require_json_object(await request.json(), "emulator.append_values")
            values = body.get("values")
            if not isinstance(values, list):
                return JSONResponse(
                    status_code=400,
                    content=google_error(400, "INVALID_ARGUMENT", "values required"),
                )
            sheet_name, _ = _split_a1(range_a1)
            sheet = _find_sheet(record.sheets, sheet_name)
            start_row = _next_empty_row(sheet)
            written = _write_at(sheet, start_row, 0, values)
            return JSONResponse(
                {
                    "spreadsheetId": spreadsheet_id,
                    "tableRange": f"{sheet.title}!A1",
                    "updates": {
                        "spreadsheetId": spreadsheet_id,
                        "updatedRange": f"{sheet.title}!A{start_row + 1}",
                        "updatedRows": written["rows"],
                        "updatedColumns": written["cols"],
                        "updatedCells": written["cells"],
                    },
                }
            )
        if decoded.endswith(":clear") and request.method == "POST":
            range_a1 = decoded[: -len(":clear")]
            _clear_range(record.sheets, range_a1)
            return JSONResponse(
                {"spreadsheetId": spreadsheet_id, "clearedRange": range_a1}
            )
        if request.method == "GET":
            values = _read_range(record.sheets, decoded)
            return JSONResponse(
                {"range": decoded, "majorDimension": "ROWS", "values": values}
            )
        if request.method == "PUT":
            body = require_json_object(await request.json(), "emulator.update_values")
            values = body.get("values")
            if not isinstance(values, list):
                return JSONResponse(
                    status_code=400,
                    content=google_error(400, "INVALID_ARGUMENT", "values required"),
                )
            updated = _write_range(record.sheets, decoded, values)
            return JSONResponse(
                {
                    "spreadsheetId": spreadsheet_id,
                    "updatedRange": decoded,
                    "updatedRows": updated["rows"],
                    "updatedColumns": updated["cols"],
                    "updatedCells": updated["cells"],
                }
            )
        return JSONResponse(
            status_code=405,
            content=google_error(405, "METHOD_NOT_SUPPORTED", "Unsupported method"),
        )

    @app.post("/v4/spreadsheets/{spreadsheet_id}:batchUpdate")
    async def spreadsheet_batch_update(
        spreadsheet_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_spreadsheet(spreadsheet_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Spreadsheet not found: {spreadsheet_id}"
                ),
            )
        body = require_json_object(await request.json(), "emulator.ss_batch_update")
        requests_raw = body.get("requests")
        replies: list[JsonObject] = []
        if isinstance(requests_raw, list):
            for req in requests_raw:
                if not isinstance(req, dict):
                    continue
                if "addSheet" in req:
                    add = req["addSheet"]
                    props = add.get("properties") if isinstance(add, dict) else None
                    title = "Sheet"
                    if isinstance(props, dict):
                        t = props.get("title")
                        if isinstance(t, str) and t.strip():
                            title = t.strip()
                    sheet_id = store.next_sheet_id_global
                    store.next_sheet_id_global += 1
                    index = len(record.sheets)
                    record.sheets.append(
                        SheetTab(sheet_id=sheet_id, title=title, index=index)
                    )
                    replies.append(
                        {
                            "addSheet": {
                                "properties": {
                                    "sheetId": sheet_id,
                                    "title": title,
                                    "index": index,
                                }
                            }
                        }
                    )
                elif "updateSheetProperties" in req:
                    upd = req["updateSheetProperties"]
                    props = upd.get("properties") if isinstance(upd, dict) else None
                    if isinstance(props, dict):
                        sheet_id = props.get("sheetId")
                        new_title = props.get("title")
                        if isinstance(sheet_id, int) and isinstance(new_title, str):
                            for sheet in record.sheets:
                                if sheet.sheet_id == sheet_id:
                                    sheet.title = new_title
                                    break
                    replies.append({"updateSheetProperties": {}})
                elif "deleteSheet" in req:
                    delete = req["deleteSheet"]
                    sheet_id = (
                        delete.get("sheetId") if isinstance(delete, dict) else None
                    )
                    if isinstance(sheet_id, int):
                        record.sheets = [
                            sheet
                            for sheet in record.sheets
                            if sheet.sheet_id != sheet_id
                        ]
                        for index, sheet in enumerate(record.sheets):
                            sheet.index = index
                    replies.append({"deleteSheet": {}})
        return JSONResponse({"spreadsheetId": spreadsheet_id, "replies": replies})

    @app.post("/v1/documents")
    async def create_document(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        body = require_json_object(await request.json(), "emulator.create_document")
        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "Untitled"
        record = store.create_document(title.strip())
        return JSONResponse(document_to_json(record))

    @app.get("/v1/documents/{document_id}")
    async def get_document(
        document_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_document(document_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Document not found: {document_id}"
                ),
            )
        return JSONResponse(document_to_json(record))

    @app.post("/v1/documents/{document_id}:batchUpdate")
    async def docs_batch_update(
        document_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        record = store.get_document(document_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content=google_error(
                    404, "NOT_FOUND", f"Document not found: {document_id}"
                ),
            )
        body = require_json_object(await request.json(), "emulator.docs_batch_update")
        requests_raw = body.get("requests")
        replies: list[JsonObject] = []
        if isinstance(requests_raw, list):
            for req in requests_raw:
                if not isinstance(req, dict):
                    continue
                if "insertText" in req:
                    insert = req["insertText"]
                    if isinstance(insert, dict):
                        text = insert.get("text")
                        location = insert.get("location")
                        index = 1
                        if isinstance(location, dict):
                            raw_index = location.get("index")
                            if isinstance(raw_index, int):
                                index = raw_index
                        if isinstance(text, str):
                            _insert_doc_text(record, index, text)
                    replies.append({"insertText": {}})
                elif "replaceAllText" in req:
                    replace = req["replaceAllText"]
                    changed = 0
                    if isinstance(replace, dict):
                        contains = replace.get("containsText")
                        replace_text = replace.get("replaceText")
                        find = ""
                        if isinstance(contains, dict):
                            t = contains.get("text")
                            if isinstance(t, str):
                                find = t
                        if isinstance(replace_text, str) and find:
                            changed = record.text.count(find)
                            record.text = record.text.replace(find, replace_text)
                    replies.append(
                        {
                            "replaceAllText": {
                                "occurrencesChanged": changed,
                            }
                        }
                    )
                elif "deleteContentRange" in req:
                    delete = req["deleteContentRange"]
                    if isinstance(delete, dict):
                        rng = delete.get("range")
                        if isinstance(rng, dict):
                            start = rng.get("startIndex")
                            end = rng.get("endIndex")
                            if isinstance(start, int) and isinstance(end, int):
                                _delete_doc_range(record, start, end)
                    replies.append({"deleteContentRange": {}})
        return JSONResponse({"documentId": document_id, "replies": replies})

    @app.post("/upload/drive/v3/files")
    async def upload_file(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        uploadType: Annotated[str | None, Query()] = None,
        fields: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        _ = uploadType
        _ = fields
        denied = _auth(authorization)
        if denied is not None:
            return denied
        _ = await request.body()
        record = store.create_document("Uploaded")
        return JSONResponse(
            {
                "id": record.document_id,
                "name": record.title,
                "mimeType": "application/vnd.google-apps.document",
                "webViewLink": (
                    f"https://docs.google.com/document/d/{record.document_id}/edit"
                ),
            }
        )

    @app.post("/drive/v3/files/{file_id}/permissions")
    async def create_permission(
        file_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        denied = _auth(authorization)
        if denied is not None:
            return denied
        if store.get_spreadsheet(file_id) is None and store.get_document(file_id) is None:
            return JSONResponse(
                status_code=404,
                content=google_error(404, "NOT_FOUND", f"File not found: {file_id}"),
            )
        body = require_json_object(await request.json(), "emulator.permissions")
        perms = store.permissions.setdefault(file_id, [])
        permission_id = f"perm_{len(perms) + 1}"
        stored = {**body, "id": permission_id}
        perms.append(stored)
        return JSONResponse(stored)

    return app


def _split_a1(range_a1: str) -> tuple[str, str]:
    if "!" in range_a1:
        sheet, cell = range_a1.split("!", 1)
        return sheet.strip("'"), cell
    return range_a1, "A1"


def _col_to_index(col: str) -> int:
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _find_sheet(sheets: list[SheetTab], title: str) -> SheetTab:
    for sheet in sheets:
        if sheet.title == title:
            return sheet
    if sheets:
        return sheets[0]
    raise ValueError("no sheets")


def _read_range(sheets: list[SheetTab], range_a1: str) -> list[list[str]]:
    sheet_name, cell = _split_a1(range_a1)
    sheet = _find_sheet(sheets, sheet_name)
    match = re.match(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", cell, re.IGNORECASE)
    if match is None:
        if not sheet.cells:
            return []
        max_row = max(sheet.cells)
        max_col = max((max(cols) for cols in sheet.cells.values()), default=0)
        return [
            [sheet.cells.get(row, {}).get(col, "") for col in range(0, max_col + 1)]
            for row in range(0, max_row + 1)
        ]
    c1 = _col_to_index(match.group(1))
    r1 = int(match.group(2)) - 1
    c2 = _col_to_index(match.group(3)) if match.group(3) else c1
    r2 = int(match.group(4)) - 1 if match.group(4) else r1
    return [
        [sheet.cells.get(row, {}).get(col, "") for col in range(c1, c2 + 1)]
        for row in range(r1, r2 + 1)
    ]


def _write_range(
    sheets: list[SheetTab],
    range_a1: str,
    values: list[JsonValue],
) -> dict[str, int]:
    sheet_name, cell = _split_a1(range_a1)
    sheet = _find_sheet(sheets, sheet_name)
    match = re.match(r"([A-Z]+)(\d+)", cell, re.IGNORECASE)
    start_col = _col_to_index(match.group(1)) if match else 0
    start_row = int(match.group(2)) - 1 if match else 0
    return _write_at(sheet, start_row, start_col, values)


def _write_at(
    sheet: SheetTab,
    start_row: int,
    start_col: int,
    values: list[JsonValue],
) -> dict[str, int]:
    rows = 0
    cols = 0
    cells = 0
    for r_offset, row_raw in enumerate(values):
        if not isinstance(row_raw, list):
            continue
        rows += 1
        for c_offset, cell in enumerate(row_raw):
            cols = max(cols, c_offset + 1)
            sheet.cells.setdefault(start_row + r_offset, {})[
                start_col + c_offset
            ] = "" if cell is None else str(cell)
            cells += 1
    return {"rows": rows, "cols": cols, "cells": cells}


def _clear_range(sheets: list[SheetTab], range_a1: str) -> None:
    sheet_name, cell = _split_a1(range_a1)
    sheet = _find_sheet(sheets, sheet_name)
    match = re.match(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", cell, re.IGNORECASE)
    if match is None:
        sheet.cells.clear()
        return
    c1 = _col_to_index(match.group(1))
    r1 = int(match.group(2)) - 1
    c2 = _col_to_index(match.group(3)) if match.group(3) else c1
    r2 = int(match.group(4)) - 1 if match.group(4) else r1
    for row in range(r1, r2 + 1):
        if row not in sheet.cells:
            continue
        for col in range(c1, c2 + 1):
            sheet.cells[row].pop(col, None)


def _next_empty_row(sheet: SheetTab) -> int:
    if not sheet.cells:
        return 0
    return max(sheet.cells) + 1


def _insert_doc_text(record: DocumentRecord, index: int, text: str) -> None:
    body = record.text if record.text.endswith("\n") else record.text + "\n"
    offset = max(index - 1, 0)
    if offset > len(body):
        offset = len(body)
    record.text = body[:offset] + text + body[offset:]


def _delete_doc_range(record: DocumentRecord, start_index: int, end_index: int) -> None:
    body = record.text
    start = max(start_index - 1, 0)
    end = max(end_index - 1, start)
    record.text = body[:start] + body[end:]
