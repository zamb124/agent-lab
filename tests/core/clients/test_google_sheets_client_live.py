"""
Live Google Sheets API — реальный HTTP, без monkeypatch/httpx fake.

Auth (один из путей):
  - OAuth: google_workspace.live_test.access_token или GOOGLE_ACCESS_TOKEN
  - SA: google_service_account.json + GOOGLE_IMPERSONATE_EMAIL (Workspace DWD)

Запуск:
  GOOGLE_ACCESS_TOKEN=ya29... \\
    uv run pytest tests/core/clients/test_google_sheets_client_live.py -m network -v -s
"""

from __future__ import annotations

import pytest

from core.clients.google_sheets_client import GoogleSheetsApiError, GoogleSheetsClient
from core.clients.google_sheets_models import (
    DriveShareRole,
    InsertDataOption,
    ValueInputOption,
    ValueRangeWrite,
    ValueRenderOption,
)
from tests.fixtures.google_sheets_live import (
    google_sheets_service_account_client_email,
    make_google_sheets_client,
    require_google_sheets_live_credentials,
)

pytestmark = [pytest.mark.network, pytest.mark.timeout(120)]


@pytest.fixture(autouse=True)
def _require_live_sheets() -> None:
    require_google_sheets_live_credentials()


@pytest.fixture()
def sheets_client() -> GoogleSheetsClient:
    return make_google_sheets_client()


@pytest.mark.asyncio
async def test_full_values_and_structure_lifecycle(
    sheets_client: GoogleSheetsClient, unique_id: str
) -> None:
    title = f"sheets-live-{unique_id}"
    created = await sheets_client.create_spreadsheet(
        title,
        sheet_titles=["Main", "Side"],
    )
    sid = created.spreadsheet_id
    assert created.title == title
    assert f"/spreadsheets/d/{sid}/" in created.web_url

    meta = await sheets_client.get_metadata(sid)
    assert meta.spreadsheet_id == sid
    assert meta.title == title
    titles = {sheet.title for sheet in meta.sheets}
    assert "Main" in titles
    assert "Side" in titles

    listed = await sheets_client.list_sheets(sid)
    assert set(listed.titles) == titles

    updated = await sheets_client.update_values(
        sid,
        "Main!A1:C2",
        [
            ["name", "qty", "total"],
            ["alpha", 2, "=B2*10"],
        ],
        value_input_option=ValueInputOption.USER_ENTERED,
    )
    assert updated.spreadsheet_id == sid
    assert updated.updated_cells is not None
    assert updated.updated_cells >= 5

    formatted = await sheets_client.get_values(
        sid,
        "Main!A1:C2",
        value_render_option=ValueRenderOption.FORMATTED_VALUE,
    )
    assert formatted.values[0] == ["name", "qty", "total"]
    assert formatted.values[1][0] == "alpha"
    assert formatted.values[1][1] in (2, 2.0, "2")

    formulas = await sheets_client.get_values(
        sid,
        "Main!C2",
        value_render_option=ValueRenderOption.FORMULA,
    )
    assert formulas.values
    assert formulas.values[0][0] == "=B2*10"

    raw_write = await sheets_client.update_values(
        sid,
        "Main!E1",
        [["=1+1"]],
        value_input_option=ValueInputOption.RAW,
    )
    assert raw_write.updated_cells == 1
    raw_read = await sheets_client.get_values(
        sid,
        "Main!E1",
        value_render_option=ValueRenderOption.FORMATTED_VALUE,
    )
    assert raw_read.values[0][0] == "=1+1"

    batch_got = await sheets_client.batch_get_values(
        sid,
        ["Main!A1:A2", "Main!B1:B2"],
    )
    assert batch_got.spreadsheet_id == sid
    assert len(batch_got.value_ranges) == 2

    batch_upd = await sheets_client.batch_update_values(
        sid,
        [
            ValueRangeWrite(range_a1="Main!A3", values=[["beta"]]),
            ValueRangeWrite(range_a1="Main!B3", values=[[3]]),
        ],
        value_input_option=ValueInputOption.USER_ENTERED,
    )
    assert batch_upd.spreadsheet_id == sid
    assert len(batch_upd.responses) >= 1

    appended = await sheets_client.append_rows(
        sid,
        "Main!A:C",
        [["gamma", 4, 40]],
        value_input_option=ValueInputOption.USER_ENTERED,
        insert_data_option=InsertDataOption.INSERT_ROWS,
    )
    assert appended.spreadsheet_id == sid
    assert appended.updated_range is not None

    cleared = await sheets_client.clear_values(sid, "Main!E1")
    assert cleared.cleared_range
    after_clear = await sheets_client.get_values(sid, "Main!E1")
    assert after_clear.values == []

    batch_clear = await sheets_client.batch_clear_values(
        sid, ["Main!A3", "Main!B3"]
    )
    assert batch_clear.spreadsheet_id == sid

    added = await sheets_client.add_sheet(sid, f"Extra-{unique_id}")
    assert added.title == f"Extra-{unique_id}"
    assert added.sheet_id >= 0

    renamed = await sheets_client.rename_sheet(
        sid, added.sheet_id, f"Renamed-{unique_id}"
    )
    assert renamed.title == f"Renamed-{unique_id}"

    deleted = await sheets_client.delete_sheet(sid, added.sheet_id)
    assert deleted.sheet_id == added.sheet_id
    after_delete = await sheets_client.list_sheets(sid)
    assert f"Renamed-{unique_id}" not in after_delete.titles

    shared = await sheets_client.share(
        sid, role=DriveShareRole.READER, anyone=True
    )
    assert shared.file_id == sid
    assert shared.anyone is True
    assert shared.role == DriveShareRole.READER

    sa_email = google_sheets_service_account_client_email()
    shared_email = await sheets_client.share(
        sid,
        role=DriveShareRole.WRITER,
        email=sa_email,
    )
    assert shared_email.anyone is False
    assert shared_email.email == sa_email


@pytest.mark.asyncio
async def test_api_error_unknown_spreadsheet(
    sheets_client: GoogleSheetsClient,
) -> None:
    with pytest.raises(GoogleSheetsApiError) as exc_info:
        await sheets_client.get_metadata("this-spreadsheet-id-does-not-exist-000")
    assert exc_info.value.status_code in (400, 403, 404)


@pytest.mark.asyncio
async def test_client_rejects_empty_title_without_http(
    sheets_client: GoogleSheetsClient,
) -> None:
    with pytest.raises(ValueError, match="title is required"):
        await sheets_client.create_spreadsheet("   ")


@pytest.mark.asyncio
async def test_client_rejects_empty_range_without_http(
    sheets_client: GoogleSheetsClient, unique_id: str
) -> None:
    created = await sheets_client.create_spreadsheet(f"range-guard-{unique_id}")
    with pytest.raises(ValueError, match="range must be non-empty"):
        await sheets_client.get_values(created.spreadsheet_id, "  ")


@pytest.mark.asyncio
async def test_share_requires_email_or_anyone(
    sheets_client: GoogleSheetsClient, unique_id: str
) -> None:
    created = await sheets_client.create_spreadsheet(f"share-guard-{unique_id}")
    with pytest.raises(ValueError, match="email is required"):
        await sheets_client.share(created.spreadsheet_id, anyone=False)
