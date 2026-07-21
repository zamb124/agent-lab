"""
Google Sheets/Docs clients against local API emulator.

Real clients + real HTTP; no monkeypatch of client methods.
Auth modes: OAuth bearer and Service Account (token via emulator /token).
"""

from __future__ import annotations

import pytest

from core.clients.google_docs_client import GoogleDocsClient, GoogleDocsClientError
from core.clients.google_sheets_client import GoogleSheetsApiError, GoogleSheetsClient
from core.clients.google_sheets_models import (
    DriveShareRole,
    InsertDataOption,
    ValueInputOption,
    ValueRangeWrite,
)
from tests.fixtures.google_api_emulator import GoogleApiEmulatorHandle


def _sheets_oauth(handle: GoogleApiEmulatorHandle) -> GoogleSheetsClient:
    return GoogleSheetsClient(access_token=handle.oauth_token)


def _sheets_sa(handle: GoogleApiEmulatorHandle) -> GoogleSheetsClient:
    return GoogleSheetsClient(
        credentials_json=handle.service_account_json(),
        subject="user@example.com",
    )


def _docs_oauth(handle: GoogleApiEmulatorHandle) -> GoogleDocsClient:
    return GoogleDocsClient(access_token=handle.oauth_token)


def _docs_sa(handle: GoogleApiEmulatorHandle) -> GoogleDocsClient:
    return GoogleDocsClient(
        credentials_json=handle.service_account_json(),
        subject="user@example.com",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_mode", ["oauth", "sa"])
async def test_sheets_full_public_surface(
    google_api_emulator: GoogleApiEmulatorHandle,
    auth_mode: str,
    unique_id: str,
) -> None:
    client = (
        _sheets_oauth(google_api_emulator)
        if auth_mode == "oauth"
        else _sheets_sa(google_api_emulator)
    )
    title = f"emu-sheets-{unique_id}"
    created = await client.create_spreadsheet(title, sheet_titles=["Main"])
    sid = created.spreadsheet_id
    assert created.title == title

    meta = await client.get_metadata(sid)
    assert meta.title == title
    assert any(sheet.title == "Main" for sheet in meta.sheets)

    listed = await client.list_sheets(sid)
    assert "Main" in listed.titles

    updated = await client.update_values(
        sid,
        "Main!A1:B2",
        [["a", "b"], ["1", "2"]],
        value_input_option=ValueInputOption.RAW,
    )
    assert updated.updated_cells == 4

    got = await client.get_values(sid, "Main!A1:B2")
    assert got.values == [["a", "b"], ["1", "2"]]

    batch_got = await client.batch_get_values(sid, ["Main!A1", "Main!B2"])
    assert len(batch_got.value_ranges) == 2
    assert batch_got.value_ranges[0].values == [["a"]]
    assert batch_got.value_ranges[1].values == [["2"]]

    batch_upd = await client.batch_update_values(
        sid,
        [
            ValueRangeWrite(range_a1="Main!C1", values=[["c"]]),
            ValueRangeWrite(range_a1="Main!C2", values=[["3"]]),
        ],
        value_input_option=ValueInputOption.RAW,
    )
    assert batch_upd.total_updated_cells == 2

    appended = await client.append_rows(
        sid,
        "Main!A:C",
        [["x", "y", "z"]],
        value_input_option=ValueInputOption.RAW,
        insert_data_option=InsertDataOption.INSERT_ROWS,
    )
    assert appended.updated_rows == 1

    cleared = await client.clear_values(sid, "Main!A1:B1")
    assert cleared.cleared_range == "Main!A1:B1"

    batch_cleared = await client.batch_clear_values(sid, ["Main!C1:C2"])
    assert batch_cleared.cleared_ranges == ["Main!C1:C2"]

    added = await client.add_sheet(sid, "Extra")
    assert added.title == "Extra"
    renamed = await client.rename_sheet(sid, added.sheet_id, "Renamed")
    assert renamed.title == "Renamed"
    deleted = await client.delete_sheet(sid, added.sheet_id)
    assert deleted.sheet_id == added.sheet_id

    shared_email = await client.share(
        sid, email="peer@example.com", role=DriveShareRole.WRITER
    )
    assert shared_email.email == "peer@example.com"
    assert shared_email.anyone is False

    shared_anyone = await client.share(sid, anyone=True, role=DriveShareRole.READER)
    assert shared_anyone.anyone is True


@pytest.mark.asyncio
async def test_sheets_unknown_id_404(
    google_api_emulator: GoogleApiEmulatorHandle,
) -> None:
    client = _sheets_oauth(google_api_emulator)
    with pytest.raises(GoogleSheetsApiError) as exc_info:
        _ = await client.get_metadata("ss_missing_id")
    assert exc_info.value.status_code == 404
    assert exc_info.value.google_error_status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_sheets_unauthorized(
    google_api_emulator: GoogleApiEmulatorHandle,
) -> None:
    _ = google_api_emulator
    client = GoogleSheetsClient(access_token="invalid-token")
    with pytest.raises(GoogleSheetsApiError) as exc_info:
        _ = await client.create_spreadsheet("nope")
    assert exc_info.value.status_code == 401
    assert exc_info.value.google_error_status == "UNAUTHENTICATED"


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_mode", ["oauth", "sa"])
async def test_docs_full_public_surface(
    google_api_emulator: GoogleApiEmulatorHandle,
    auth_mode: str,
    unique_id: str,
) -> None:
    client = (
        _docs_oauth(google_api_emulator)
        if auth_mode == "oauth"
        else _docs_sa(google_api_emulator)
    )
    created = await client.create_document(f"emu-doc-{unique_id}")
    doc_id = created["documentId"]
    assert isinstance(doc_id, str)

    await client.append_text(doc_id, "Hello world.")
    text = await client.read_as_text(doc_id)
    assert "Hello world." in text

    await client.insert_text(doc_id, "PREFIX ", index=1)
    text = await client.read_as_text(doc_id)
    assert text.startswith("PREFIX ")

    await client.find_and_replace(doc_id, "world", "planet")
    text = await client.read_as_text(doc_id)
    assert "planet" in text
    assert "world" not in text

    await client.delete_range(doc_id, 1, 7)
    text = await client.read_as_text(doc_id)
    assert not text.startswith("PREFIX")

    uploaded = await client.upload_docx(f"upload-{unique_id}", b"PK\x03\x04fake-docx")
    assert isinstance(uploaded["id"], str)
    assert uploaded["mimeType"] == "application/vnd.google-apps.document"

    shared = await client.share_document(doc_id, "reader@example.com", role="reader")
    assert shared["emailAddress"] == "reader@example.com"
    anyone = await client.share_document_anyone(doc_id, role="commenter")
    assert anyone["type"] == "anyone"


@pytest.mark.asyncio
async def test_docs_unknown_id_404(
    google_api_emulator: GoogleApiEmulatorHandle,
) -> None:
    client = _docs_oauth(google_api_emulator)
    with pytest.raises(GoogleDocsClientError) as exc_info:
        _ = await client.get_document("doc_missing")
    assert exc_info.value.status_code == 404
