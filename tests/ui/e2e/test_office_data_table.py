"""E2E: Documents editor host for DataTable — types, edit, delete, CSV/xlsx."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.async_api import Page, expect

from core.data_tables.import_tabular import parse_tabular_bytes
from tests.ui.e2e.office_e2e_helpers import (
    office_e2e_expect_editor_loaded,
    office_e2e_namespace_headers,
    office_e2e_open_with_namespace,
)
from tests.ui.harness import AppUI

_SQLITE_MAGIC = b"SQLite format 3"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_data_table_host_edit_delete_and_tabular_export(
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system, frontend_di,
) -> None:
    namespace = await office_e2e_open_with_namespace(
        office_ui, ui_page_system, unique_id, suffix="dtable", di=frontend_di
    )
    headers = office_e2e_namespace_headers(auth_headers_system, namespace)
    original_name = f"e2e-table-{unique_id}.sqlite"
    create_response = await office_client_http.post(
        "/documents/api/v1/data-tables",
        headers=headers,
        json={
            "original_name": original_name,
            "scope": "office_document",
            "namespace": namespace,
            "tables": [
                {
                    "name": "leads",
                    "columns": [
                        {"name": "title", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                    ],
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    file_id = create_response.json()["file_id"]
    insert_response = await office_client_http.post(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=headers,
        json={"rows": [{"title": "Ada", "score": 10}]},
    )
    assert insert_response.status_code == 200, insert_response.text

    await ui_page_system.goto(
        f"{office_ui.origin}/documents/edit/{file_id}",
        wait_until="domcontentloaded",
    )
    await office_e2e_expect_editor_loaded(ui_page_system)
    host = ui_page_system.locator("platform-data-table-host").first
    await expect(host).to_be_visible(timeout=60_000)
    await expect(host.locator("td.cell-editable").first).to_be_visible(timeout=30_000)
    await expect(host.get_by_role("button", name="Скачать CSV")).to_be_visible()
    await expect(host.get_by_role("button", name="Скачать Excel")).to_be_visible()
    await expect(host.get_by_role("button", name="Скачать", exact=True)).to_have_count(0)

    title_cell = host.locator("td.cell-editable").first
    async with ui_page_system.expect_response(
        lambda response: "/rows/" in response.url
        and response.request.method == "PATCH"
        and response.ok
    ):
        await title_cell.click()
        editor = host.locator("input[data-canon='inline-edit']")
        await expect(editor).to_be_visible(timeout=5_000)
        await editor.fill("Grace")
        await editor.press("Enter")

    page_after_edit = await office_client_http.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=headers,
        params={"limit": 50},
    )
    assert page_after_edit.status_code == 200, page_after_edit.text
    assert page_after_edit.json()["items"][0]["values"]["title"] == "Grace"
    assert page_after_edit.json()["items"][0]["values"]["score"] == 10

    score_cell = host.locator("td.cell-editable").nth(1)
    await score_cell.click()
    score_editor = host.locator("input[data-canon='inline-edit']")
    await expect(score_editor).to_be_visible(timeout=5_000)
    await score_editor.fill("nope")
    await score_editor.press("Enter")
    await expect(host.locator("p.form-error.banner")).to_be_visible(timeout=10_000)
    rejected_page = await office_client_http.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=headers,
        params={"limit": 50},
    )
    assert rejected_page.json()["items"][0]["values"]["score"] == 10

    async with ui_page_system.expect_download() as csv_download:
        await host.get_by_role("button", name="Скачать CSV").click()
    csv_file = await csv_download.value
    assert csv_file.suggested_filename.endswith(".csv")
    assert not csv_file.suggested_filename.endswith(".sqlite")
    csv_path = await csv_file.path()
    assert csv_path is not None
    csv_bytes = Path(csv_path).read_bytes()
    assert not csv_bytes.startswith(_SQLITE_MAGIC)
    csv_columns, csv_rows = parse_tabular_bytes(csv_bytes, source_format="csv")
    assert [column.name for column in csv_columns] == ["title", "score"]
    assert csv_rows[0]["title"] == "Grace"

    async with ui_page_system.expect_download() as xlsx_download:
        await host.get_by_role("button", name="Скачать Excel").click()
    xlsx_file = await xlsx_download.value
    assert xlsx_file.suggested_filename.endswith(".xlsx")
    assert not xlsx_file.suggested_filename.endswith(".sqlite")
    xlsx_path = await xlsx_file.path()
    assert xlsx_path is not None
    xlsx_bytes = Path(xlsx_path).read_bytes()
    assert xlsx_bytes.startswith(b"PK")
    assert _SQLITE_MAGIC not in xlsx_bytes[:64]
    xlsx_columns, xlsx_rows = parse_tabular_bytes(xlsx_bytes, source_format="xlsx")
    assert [column.name for column in xlsx_columns] == ["title", "score"]
    assert xlsx_rows[0]["title"] == "Grace"

    async with ui_page_system.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.rstrip("/").endswith("/rows")
        and response.ok
    ):
        await host.get_by_role("button", name="Новая строка").click()
    await expect(host.locator("tbody tr")).to_have_count(2, timeout=15_000)

    await host.get_by_role("button", name="Удалить строку").last.click()
    confirm = ui_page_system.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=15_000)
    await confirm.get_by_role("button", name="Удалить строку").click()
    await expect(confirm).to_be_hidden(timeout=30_000)
    await expect(host.locator("tbody tr")).to_have_count(1, timeout=15_000)
    leftover = await office_client_http.get(
        f"/documents/api/v1/data-tables/{file_id}/tables/leads/rows",
        headers=headers,
        params={"limit": 50},
    )
    assert leftover.status_code == 200, leftover.text
    leftover_items = leftover.json()["items"]
    assert len(leftover_items) == 1
    assert leftover_items[0]["values"]["title"] == "Grace"

    await expect(
        ui_page_system.get_by_role("button", name=re.compile(r"sqlite", re.I))
    ).to_have_count(0)
